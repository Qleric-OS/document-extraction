"""
# ═══════════════════════════════════════════════════════════════════════════════
# QLERIC DOCUMENT EXTRACTOR - V1
# ═══════════════════════════════════════════════════════════════════════════════
# Version: 1.0 (Public Release)
# License: AGPL-3.0
# Copyright (C) 2026 Qleric
#
# DESCRIPTION:
# A production-grade utility for extracting structured data from PDF and DOCX 
# documents with built-in verification and cross-referencing logic.
#
# CORE FEATURES:
# 1. Verification Pass: Real-time quote validation against raw document text.
# 2. Structured Analysis: Pattern-based derivation of rights and obligations.
# 3. Multi-Format: Native support for PDF and Word documents.
# 4. Financial Normalization: Locale-aware parsing of currency and tables.
#
# USAGE:
# python contract_extractor.py my_document.pdf --fields parties,effective_date
# ═══════════════════════════════════════════════════════════════════════════════
"""

import atexit
import gc
import io
import json
import logging
import os
import re
import time
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Union
from dotenv import load_dotenv

import fitz  # PyMuPDF
import msgspec
import msgspec.yaml
import spacy
from anthropic import Anthropic, APIError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# DOCX support
try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    DocxDocument = None

load_dotenv()

# -------------------------------------------------------------------------
# Default Prompts (Fallbacks)
# -------------------------------------------------------------------------

DEFAULT_EXTRACTION_PROMPT = """You are an expert contract analyst. Extract the requested fields into JSON format.

EXTRACTION TIER: {label}

FIELDS TO EXTRACT:
{fields_list}

Instructions:
1. Extract the 'value' and 'verbatim_source' (exact substring) for each field.
2. If facets (e.g., 'favors', 'mutual', 'conditional') are explicitly requested in a field's description, include them in the JSON object for that field.
3. If not found, return null for the 'value'.
4. Return ONLY JSON.
"""

DEFAULT_RECHECK_PROMPT = """You are an expert contract analyst doing a SECOND PASS review.
The initial extraction MISSED these fields. Look for synonyms or hidden clauses.

Return JSON format with 'value', 'verbatim_source', and 'page_number'.
"""


# -------------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------------

def get_anthropic_api_key() -> str:
    """Get the Anthropic API key."""
    key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not key:
        logger.warning("No ANTHROPIC_API_KEY found in .env")
        return ""
    return key


import hashlib

def stable_hash(text: str) -> str:
    """Generate stable hash across sessions."""
    if not isinstance(text, str):
        text = str(text)
    return hashlib.md5(text.encode()).hexdigest()[:8]

def parse_days_from_text(text: str) -> Optional[int]:
    """Robust duration parser for contracts."""
    if not text:
        return None
    clean_text = text.lower().replace('-', ' ')
    clean_text = re.sub(r'\b(a|an)\s+(day|week|month|year)', r'1 \2', clean_text)
    
    word_map = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'ninety': 90
    }
    
    bracket_match = re.search(r'\((\d+)\)', clean_text)
    if bracket_match:
        val = int(bracket_match.group(1))
    else:
        for word, digit in word_map.items():
            clean_text = re.sub(r'\b' + word + r'\b', str(digit), clean_text)
        match = re.search(r'(\d+)', clean_text)
        val = int(match.group(1)) if match else None

    if val is None: return None
    if 'year' in clean_text or 'annum' in clean_text: return val * 365
    if 'month' in clean_text: return val * 30
    if 'week' in clean_text: return val * 7
    return val

def parse_absolute_date(text: str) -> Optional[str]:
    """Parse absolute dates from text."""
    patterns = [r'(\d{1,2}/\d{1,2}/\d{4})', r'(\d{4}-\d{2}-\d{2})', r'(\w+ \d{1,2}, \d{4})']
    for pattern in patterns:
        match = re.search(pattern, text)
        if match: return match.group(1)
    return None

def summarize_value(value: str) -> str:
    """Create a brief summary of a field value."""
    if not value or not isinstance(value, str): return ""
    return value[:100] + "..." if len(value) > 100 else value

def parse_currency(text: str) -> Optional[float]:
    """
    Production-grade currency parser.
    Handles: '$50k', '1.2M', 'USD 50,000.00', '€1.000,00' (EU format fallback), 'Free'
    """
    if not text:
        return None

    if isinstance(text, (int, float)):
        return float(text)
        
    clean_text = text.lower().strip()
    
    # Quick exit for zero-cost terms
    if any(x in clean_text for x in ['free', 'no cost', 'complimentary', 'included']):
        return 0.0

    # 1. Handle Multipliers (k, m, b)
    multiplier = 1.0
    if clean_text.endswith(('k', 'tho', 'thousand')):
        multiplier = 1_000.0
    elif clean_text.endswith(('m', 'mil', 'million', 'mn')):
        multiplier = 1_000_000.0
    elif clean_text.endswith(('b', 'bil', 'billion', 'bn')):
        multiplier = 1_000_000_000.0
        
    # Remove text suffix after identifying multiplier
    clean_text = re.sub(r'[a-z]+$', '', clean_text).strip()

    # 2. Extract numeric part
    match = re.search(r'[\d.,]+', clean_text)
    if not match:
        return None
        
    number_str = match.group(0)
    
    # 3. Handle Locale (Comma vs Dot)
    try:
        if ',' in number_str and '.' in number_str:
            last_comma = number_str.rfind(',')
            last_dot = number_str.rfind('.')
            if last_comma > last_dot: # EU Style: 10.000,00
                number_str = number_str.replace('.', '').replace(',', '.')
            else: # US Style: 10,000.00
                number_str = number_str.replace(',', '')
        elif ',' in number_str:
            if re.search(r',\d{3}$', number_str) or re.search(r',\d{3}\D', number_str):
                 number_str = number_str.replace(',', '')
            else:
                 number_str = number_str.replace(',', '.')
                 
        val = float(number_str)
        return val * multiplier
    except ValueError:
        return None

def extract_currency(text: str) -> str:
    """Extract currency code."""
    if isinstance(text, (int, float)): return 'USD'
    tx = text.upper()
    if '$' in tx or 'USD' in tx: return 'USD'
    if '€' in tx or 'EUR' in tx: return 'EUR'
    if '£' in tx or 'GBP' in tx: return 'GBP'
    return 'USD'

def infer_payment_structure(field_name: str, value: str) -> Dict:
    """Infer payment structure."""
    if field_name == "total_contract_value": return {"type": "fixed"}
    vl = value.lower()
    if "monthly" in vl: return {"type": "recurring", "frequency": "monthly"}
    if "annual" in vl: return {"type": "recurring", "frequency": "annual"}
    return {"type": "fixed"}

def parse_exceptions(text: str) -> List[str]:
    """Parse common legal exceptions."""
    exceptions = []
    tx = text.lower()
    if "gross negligence" in tx: exceptions.append("gross_negligence")
    if "willful misconduct" in tx: exceptions.append("willful_misconduct")
    return exceptions

def parse_penalty_calculation(text: str) -> Dict:
    """Parse penalty calculation logic."""
    if "%" in text:
        match = re.search(r'(\d+(?:\.\d+)?)%', text)
        if match: return {"type": "percentage", "rate": float(match.group(1)), "period": "monthly"}
    return {"type": "fixed", "amount": parse_currency(text) or 0}

def link_to_obligation(field_name: str) -> str:
    """Map penalty field to source obligation."""
    mapping = {"late_fees": "payment_terms", "penalties": "sla_terms"}
    return mapping.get(field_name, "general_obligations")

def generate_risk_description(risk_type: str, field_data: Dict) -> str:
    """Generate human-readable risk description."""
    descriptions = {
        "uncapped_liability": "No limit on liability exposure detected",
        "asymmetric_termination": "Termination rights significantly favor one party",
        "no_cure_period": "No period allowed to fix breaches before termination",
        "no_exit_clause": "No right for termination for convenience found"
    }
    return descriptions.get(risk_type, f"Risk detected: {risk_type}")

def extract_conditions_from_value(value: str) -> str:
    """Extract preconditions from text."""
    if not value or not isinstance(value, str): return ""
    return value[:50] + "..." if len(value) > 50 else value


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER FIELD BANK - 60+ fields across comprehensive categories
# ═══════════════════════════════════════════════════════════════════════════════

MASTER_FIELD_BANK = {
    # ═══════════════════════════════════════════════════════════════════════════
    # CORE DATES & PARTIES (3 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "dates_parties": {
        "effective_date",
        "expiration_date",
        "parties",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FINANCIAL TERMS (3 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "financial_basic": {
        "total_contract_value",
        "payment_terms",
        "currency",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TERMINATION & RENEWAL (3 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "termination_basic": {
        "termination_notice_period",
        "renewal_terms",
        "governing_law",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # LIABILITY & RISK - BASIC (4 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "liability_basic": {
        "liability_cap",
        "indemnification_clauses",
        "insurance_requirements",
        "limitation_of_liability",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE & OBLIGATIONS - BASIC (4 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "performance_basic": {
        "deliverables",
        "sla_terms",
        "performance_metrics",
        "acceptance_criteria",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # INTELLECTUAL PROPERTY - BASIC (3 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "ip_basic": {
        "ip_ownership",
        "license_scope",
        "usage_restrictions",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # COMPLIANCE & DISPUTE - BASIC (5 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "compliance_basic": {
        "confidentiality_period",
        "non_compete_terms",
        "arbitration_clause",
        "audit_rights",
        "data_protection",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ADMINISTRATIVE - BASIC (4 fields)
    # ═══════════════════════════════════════════════════════════════════════════
    "administrative_basic": {
        "notice_address",
        "amendment_process",
        "assignment_rights",
        "force_majeure",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PAYMENT WORKFLOW - EXTENDED (5 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "payment_workflow": {
        "late_fees",
        "payment_milestones",
        "invoice_frequency",
        "dispute_procedures",
        "escrow_terms",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # COMPLIANCE EXTENDED (5 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "compliance_extended": {
        "gdpr_obligations",
        "ccpa_compliance",
        "security_standards",
        "audit_frequency",
        "certification_requirements",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE EXTENDED (5 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "performance_extended": {
        "penalties",
        "cure_periods",
        "escalation_procedures",
        "change_order_process",
        "warranty_terms",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RISK MANAGEMENT (4 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "risk_management": {
        "risk_allocation",
        "contingency_provisions",
        "material_breach_definition",
        "remedies",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TERMINATION EXTENDED (4 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "termination_extended": {
        "termination_for_cause",
        "termination_for_convenience",
        "transition_assistance",
        "survival_clauses",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # IP EXTENDED (5 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "ip_extended": {
        "background_ip",
        "foreground_ip",
        "joint_ip",
        "moral_rights_waiver",
        "source_code_escrow",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # COMMERCIAL TERMS (5 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "commercial_terms": {
        "exclusivity",
        "territory_restrictions",
        "volume_commitments",
        "price_adjustments",
        "benchmarking_rights",
    },
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RELATIONSHIP TERMS (4 fields) [NEW]
    # ═══════════════════════════════════════════════════════════════════════════
    "relationship_terms": {
        "subcontracting_rights",
        "key_personnel",
        "governance_structure",
        "reporting_requirements",
    },
}

# Flatten all fields for validation
ALL_FIELDS = set()
for category_fields in MASTER_FIELD_BANK.values():
    ALL_FIELDS.update(category_fields)

# ═══════════════════════════════════════════════════════════════════════════════
# TIERED FIELD DEFINITIONS - Built from Master Bank
# Default extraction fields (25 most critical fields for pass-1 / general analysis)
DEFAULT_FIELDS = (
    MASTER_FIELD_BANK["dates_parties"] |
    MASTER_FIELD_BANK["financial_basic"] |
    MASTER_FIELD_BANK["termination_basic"] |
    MASTER_FIELD_BANK["liability_basic"] |
    MASTER_FIELD_BANK["performance_basic"] |
    MASTER_FIELD_BANK["ip_basic"] |
    MASTER_FIELD_BANK["compliance_basic"]
)

# Contract type categories for classification
CONTRACT_TYPES = [
    "Service Agreement",
    "Employment Contract",
    "Non-Disclosure Agreement",
    "License Agreement",
    "Sales Agreement",
    "Lease Agreement",
    "Partnership Agreement",
    "Consulting Agreement",
    "Supply Agreement",
    "Vendor Agreement",
    "Master Services Agreement",
    "Statement of Work",
    "General Agreement",  # Fallback
]

# Credit calculation for custom field selection (mix-match)
def calculate_custom_credits(field_count: int) -> int:
    """
    Calculate credits based on number of fields selected.
    Enforces 25-field maximum limit.
    """
    if field_count > MAX_CUSTOM_FIELDS:
        raise ValueError(f"Maximum {MAX_CUSTOM_FIELDS} fields allowed per extraction")
    if field_count <= 9:
        return 1
    elif field_count <= 18:
        return 3
    else:
        return 5

# Field descriptions for LLM prompting
FIELD_DESCRIPTIONS = {
    # ═══ CORE DATES & PARTIES ═══
    "effective_date": "Contract START date / Effective date",
    "expiration_date": "Contract END date / Expiration date",
    "parties": "Names of all parties/entities in the contract",
    
    # ═══ FINANCIAL TERMS ═══
    "total_contract_value": "Total monetary value of the contract (calculate if needed)",
    "payment_terms": "Payment schedule and terms (e.g., Net 30, monthly)",
    "currency": "Currency used (USD, EUR, GBP, etc.)",
    
    # ═══ TERMINATION & RENEWAL ═══
    "termination_notice_period": "Notice period required to terminate",
    "renewal_terms": "Auto-renewal conditions, renewal options",
    "governing_law": "Jurisdiction / Governing law / Choice of law",
    
    # ═══ LIABILITY & RISK ═══
    "liability_cap": "Maximum liability amount or percentage cap",
    "indemnification_clauses": "Who indemnifies whom and for what",
    "insurance_requirements": "Required insurance types and minimum amounts",
    "limitation_of_liability": "Exclusions, carve-outs from liability limits",
    
    # ═══ PERFORMANCE & OBLIGATIONS ═══
    "deliverables": "Key deliverables, milestones, or work products",
    "sla_terms": "Service Level Agreement terms and commitments",
    "performance_metrics": "KPIs, penalties for non-performance",
    "acceptance_criteria": "How deliverables/work is accepted",
    
    # ═══ INTELLECTUAL PROPERTY ═══
    "ip_ownership": "Who owns intellectual property created",
    "license_scope": "License type (exclusive, non-exclusive, perpetual)",
    "usage_restrictions": "Geographic, industry, or use-case limitations",
    
    # ═══ COMPLIANCE & DISPUTE ═══
    "confidentiality_period": "Duration of confidentiality/NDA obligations",
    "non_compete_terms": "Non-compete restrictions and duration",
    "arbitration_clause": "Dispute resolution method (arbitration, mediation, litigation)",
    "audit_rights": "Right to audit records, financials, or compliance",
    "data_protection": "GDPR, CCPA, or other data privacy obligations",
    
    # ═══ ADMINISTRATIVE ═══
    "notice_address": "Address for official notices/communications",
    "amendment_process": "How the contract can be modified",
    "assignment_rights": "Whether contract can be assigned/transferred",
    "force_majeure": "Force majeure clause presence and terms",
    
    # ═══ PAYMENT WORKFLOW (NEW) ═══
    "late_fees": "Late payment penalties, interest rates, or fee structures",
    "payment_milestones": "Milestone-based payment schedule and triggers",
    "invoice_frequency": "How often invoices are submitted (monthly, quarterly, etc.)",
    "dispute_procedures": "Process for disputing invoices or payments",
    "escrow_terms": "Escrow arrangements, holdbacks, or retainage terms",
    
    # ═══ COMPLIANCE EXTENDED (NEW) ═══
    "gdpr_obligations": "Specific GDPR compliance requirements and data handling",
    "ccpa_compliance": "California Consumer Privacy Act requirements",
    "security_standards": "Required security certifications (SOC2, ISO27001, etc.)",
    "audit_frequency": "How often audits can be conducted",
    "certification_requirements": "Required certifications or qualifications",
    
    # ═══ PERFORMANCE EXTENDED (NEW) ═══
    "penalties": "Financial penalties for non-performance or SLA breaches",
    "cure_periods": "Time allowed to remedy breaches before termination",
    "escalation_procedures": "How disputes or issues are escalated",
    "change_order_process": "Procedure for scope changes and modifications",
    "warranty_terms": "Warranty period, coverage, and limitations",
    
    # ═══ RISK MANAGEMENT (NEW) ═══
    "risk_allocation": "How risks are divided between parties",
    "contingency_provisions": "Backup plans or contingency clauses",
    "material_breach_definition": "What constitutes a material breach",
    "remedies": "Available remedies for breach (damages, specific performance)",
    
    # ═══ TERMINATION EXTENDED (NEW) ═══
    "termination_for_cause": "Grounds for termination due to breach or default",
    "termination_for_convenience": "Right to terminate without cause",
    "transition_assistance": "Obligations to help transition to new provider",
    "survival_clauses": "Provisions that survive contract termination",
    
    # ═══ IP EXTENDED (NEW) ═══
    "background_ip": "Pre-existing intellectual property each party brings",
    "foreground_ip": "New IP created during the contract",
    "joint_ip": "Jointly developed intellectual property ownership",
    "moral_rights_waiver": "Waiver of moral rights to creative works",
    "source_code_escrow": "Source code escrow arrangements for software",
    
    # ═══ COMMERCIAL TERMS (NEW) ═══
    "exclusivity": "Exclusive dealing or exclusivity provisions",
    "territory_restrictions": "Geographic limitations on rights or operations",
    "volume_commitments": "Minimum purchase or volume requirements",
    "price_adjustments": "Price escalation clauses or adjustment mechanisms",
    "benchmarking_rights": "Right to benchmark pricing against market",
    
    # ═══ RELATIONSHIP TERMS (NEW) ═══
    "subcontracting_rights": "Whether and how subcontracting is permitted",
    "key_personnel": "Named individuals critical to performance",
    "governance_structure": "Joint steering committees or governance bodies",
    "reporting_requirements": "Required reports, frequency, and format",
}

# ═══════════════════════════════════════════════════════════════════════════════
# FIELD TAXONOMY - Which fields can be citation-verified vs. which are derived
# ═══════════════════════════════════════════════════════════════════════════════
# 
# EXTRACTIVE: Value should be quoted directly from the document
# DERIVED: Value is calculated, inferred, or consolidated from multiple sources
#
# This prevents penalizing correct synthesis fields that can't have single citations

DERIVED_FIELDS = {
    # These fields often require calculation or consolidation
    "total_contract_value",      # May be sum of multiple payments
    "payment_terms",             # Often summarized from multiple clauses
    "parties",                   # Consolidated from multiple mentions
    "renewal_terms",             # May be inferred from multiple sections
    "deliverables",              # Often listed across multiple sections
    "sla_terms",                 # Typically summarized from schedules/exhibits
    "payment_milestones",        # Derived from multiple schedule entries
    "remedies",                  # May combine multiple remedy clauses
}

# All other fields are EXTRACTIVE (should have direct citation)
def is_derived_field(field_name: str) -> bool:
    """Check if a field is derived (synthesis) vs. extractive (direct quote)."""
    return field_name in DERIVED_FIELDS


# ═══════════════════════════════════════════════════════════════════════════════
# FIELD FACETS - Structured interpretation metadata for extracted fields
# ═══════════════════════════════════════════════════════════════════════════════
# 
# Facets answer "so what?" by adding structured interpretation to raw values.
# These provide bias detection by identifying favors (buyer/seller).
#
# Available facets:
#   - favors: "buyer" | "seller" | "mutual" | "neutral" - Who does this favor?
#   - mutual: bool - Is this obligation bidirectional?
#   - conditional: bool - Subject to conditions/triggers?
#   - exceptions_present: bool - Are there carve-outs/exclusions?
#   - time_bound: bool - Has explicit duration?
#   - capped: bool - Has monetary/percentage cap?

FACET_APPLICABLE_FIELDS = {
    # Termination & Renewal
    "termination_for_convenience": ["favors", "mutual", "conditional"],
    "termination_for_cause": ["favors", "mutual", "conditional"],
    "termination_notice_period": ["favors", "mutual"],
    "renewal_terms": ["favors", "conditional"],
    
    # Liability & Risk
    "liability_cap": ["favors", "mutual", "capped", "exceptions_present"],
    "indemnification_clauses": ["favors", "mutual", "capped", "exceptions_present"],
    "limitation_of_liability": ["favors", "exceptions_present"],
    "insurance_requirements": ["mutual", "capped"],
    
    # IP & Confidentiality
    "ip_ownership": ["favors"],
    "confidentiality_period": ["mutual", "time_bound", "exceptions_present"],
    "license_scope": ["favors", "time_bound"],
    
    # Performance & SLA
    "sla_terms": ["favors", "conditional", "exceptions_present"],
    "warranty_terms": ["favors", "time_bound", "capped"],
    "penalties": ["favors", "capped", "conditional"],
    "cure_periods": ["favors", "time_bound"],
    
    # Financial
    "payment_terms": ["favors", "conditional"],
    "late_fees": ["favors", "capped"],
    "price_adjustments": ["favors", "conditional", "capped"],
    
    # Administrative
    "assignment_rights": ["favors", "mutual", "conditional"],
    "audit_rights": ["favors", "mutual", "conditional"],
    "force_majeure": ["mutual", "exceptions_present"],
}


def get_applicable_facets(field_name: str) -> list:
    """Get list of applicable facets for a field."""
    return FACET_APPLICABLE_FIELDS.get(field_name, [])


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT NORMALIZATION FOR FUZZY MATCHING
# ═══════════════════════════════════════════════════════════════════════════════
# 
# Handles: line breaks, hyphenation, OCR artifacts, ligatures, extra whitespace

def normalize_text_for_matching(text: str) -> str:
    """
    Normalize text to handle PDF extraction quirks:
    - Line breaks within sentences
    - Hyphenation at line ends
    - Multiple spaces
    - Common ligatures (fi, fl, ff, ffi, ffl)
    - OCR common errors
    """
    if not text:
        return ""
    
    # Convert ligatures to regular characters
    ligature_map = {
        '\ufb01': 'fi',  # fi ligature
        '\ufb02': 'fl',  # fl ligature
        '\ufb00': 'ff',  # ff ligature
        '\ufb03': 'ffi', # ffi ligature
        '\ufb04': 'ffl', # ffl ligature
    }
    for lig, replacement in ligature_map.items():
        text = text.replace(lig, replacement)
    
    # Remove hyphenation at line breaks (word-\n -> word)
    text = re.sub(r'-\s*\n\s*', '', text)
    
    # Normalize all whitespace (newlines, tabs, multiple spaces) to single space
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    # Lowercase for comparison (but preserve original for display)
    return text.lower()


def fuzzy_text_exists(needle: str, haystack: str, threshold: float = 0.85) -> bool:
    """
    Check if needle exists in haystack with fuzzy matching.
    Handles OCR errors and PDF text extraction quirks.
    
    Returns True if:
    1. Exact normalized match exists, OR
    2. Similarity ratio >= threshold
    """
    if not needle or not haystack:
        return False
    
    # Normalize both
    norm_needle = normalize_text_for_matching(needle)
    norm_haystack = normalize_text_for_matching(haystack)
    
    # First try: exact substring match on normalized text
    if norm_needle in norm_haystack:
        return True
    
    # Second try: check if words are present (order-independent)
    needle_words = set(norm_needle.split())
    if len(needle_words) >= 3:  # Only for multi-word searches
        haystack_words = set(norm_haystack.split())
        word_overlap = len(needle_words & haystack_words) / len(needle_words)
        if word_overlap >= threshold:
            return True
    
    return False


# For backward compatibility
SUPPORTED_KEYS = DEFAULT_FIELDS

INPUT_TOKEN_COST = 0.000003
OUTPUT_TOKEN_COST = 0.000015

# 🔒 FIX: Cost alert threshold
HIGH_COST_ALERT_THRESHOLD = 1.0  # Alert if single request costs over $1

# -------------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------------

logging.getLogger().handlers.clear()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Decorators
# -------------------------------------------------------------------------

def performance_profiler(func):
    """Decorator to measure execution time and peak memory usage."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tracemalloc.start()
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        finally:
            end_time = time.perf_counter()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            if isinstance(result, dict):
                result.setdefault("performance_metrics", {})
                result["performance_metrics"].update({
                    "execution_time_seconds": f"{end_time - start_time:.4f}",
                    "peak_memory_usage_mb": f"{peak / 10**6:.2f}",
                })

        return result

    return wrapper


# -------------------------------------------------------------------------
# Data Models
# -------------------------------------------------------------------------

class ExtractionSource(Enum):
    LLM = "llm"
    HEURISTIC = "heuristic"
    SYSTEM_FALLBACK = "system_fallback"
    INFERENCE = "inference"

class ExtractionValueSource(Enum):
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    DEFAULT = "default"

class ProvenanceType(Enum):
    VERBATIM = "verbatim"
    INFERRED = "inferred"
    DEFAULTED = "defaulted"
    USER_INPUT = "user_input"

@dataclass
class ExtractionValue:
    value: Any
    source: ExtractionValueSource
    confidence: float = 1.0
    default_label: Optional[str] = None

    def to_dict(self):
        return {
            "value": self.value,
            "source": self.source.value,
            "confidence": self.confidence,
            "default_label": self.default_label
        }

def normalize_analysis_payload(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes analysis fields for backend compatibility.
    Provides verified resolution: EXTRACTED vs INFERRED vs DEFAULT.
    """
    if not isinstance(analysis, dict):
        return {}

    normalized: Dict[str, Any] = {}

    def _resolution_source(item: Dict[str, Any], field_key: str) -> ExtractionValueSource:
        # If it's a known derived field, it's inferred by definition
        if is_derived_field(field_key):
            return ExtractionValueSource.INFERRED
            
        source = str(item.get("source") or "").lower()
        if source == ExtractionSource.SYSTEM_FALLBACK.value.lower():
            return ExtractionValueSource.DEFAULT
        
        grounded = item.get("grounded", False)
        if grounded:
            return ExtractionValueSource.EXTRACTED
            
        return ExtractionValueSource.INFERRED

    for key, field in analysis.items():
        if not isinstance(field, dict) or key.startswith("_"):
            normalized[key] = field
            continue

        item = dict(field)
        val = item.get("value")
        
        # Determine source resolution
        source = _resolution_source(item, key)
        
        # Calculate confidence
        confidence = item.get("confidence_score") or (0.95 if item.get("grounded") else 0.6)
        if source == ExtractionValueSource.DEFAULT:
            confidence = 0.1

        # Attach resolution object
        item["resolution"] = ExtractionValue(
            value=val,
            source=source,
            confidence=float(confidence)
        ).to_dict()
        
        normalized[key] = item

    return normalized

def compute_document_complexity(analysis: Dict[str, Any]) -> str:
    """Analytical complexity score based on extraction results."""
    # Simple heuristic for open source version
    field_count = len([k for k in analysis if not k.startswith("_")])
    grounding_rate = sum(1 for k, v in analysis.items() if isinstance(v, dict) and v.get("grounded", False)) / max(field_count, 1)
    
    if grounding_rate > 0.9 and field_count > 15:
        return "High (Structured)"
    if grounding_rate < 0.5:
        return "Complex (Non-Standard)"
    return "Medium"

@dataclass
class ConfidenceModel:
    score: float
    threshold: float = 0.7
    is_reliable: bool = field(init=False)

    def __post_init__(self):
        self.is_reliable = self.score >= self.threshold

@dataclass
class ExtractionResult:
    value: Any
    source: ExtractionSource
    page_number: Optional[int] = None
    reference_snippet: Optional[str] = None
    bbox: Optional[List[List[float]]] = None
    grounded: bool = False
    field_type: str = "extractive"
    facets: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "value": self.value,
            "source": self.source.value,
            "page_number": self.page_number,
            "reference_snippet": self.reference_snippet,
            "bbox": self.bbox,
            "grounded": self.grounded,
            "field_type": self.field_type,
        }
        if self.facets:
            result["facets"] = self.facets
        return result


@dataclass
class PatternConfig:
    patterns: List[str]
    formatter: Optional[str] = None
    fallback_text: Optional[str] = "Not Found"
    find_all: bool = False


@dataclass
class PageText:
    page_number: int
    text: str


# -------------------------------------------------------------------------
# Main Extractor
# -------------------------------------------------------------------------

class ContractExtractor:
    """Contract information extractor using Anthropic Claude and PyMuPDF for coordinates."""

    def __init__(self):
        self.patterns: Dict[str, PatternConfig] = {}
        atexit.register(self.cleanup)

        self.nlp = spacy.blank("en")
        self.nlp.add_pipe("sentencizer")

        # Initialize Anthropic Client
        api_key = get_anthropic_api_key()
        self.client = Anthropic(api_key=api_key) if api_key else None

        # ═══════════════════════════════════════════════════════════════════════════════
        # DERIVATION BUCKETS (The Knowledge Graph Routing Logic)
        # ═══════════════════════════════════════════════════════════════════════════════

        # Bucket 2: Time-Bound Obligations
        self.TIME_BOUND_OBLIGATION_FIELDS = {
            "payment_terms": {"action": "pay", "anchor": "invoice_issued"},
            "termination_notice_period": {"action": "notify", "anchor": "intent_to_terminate"},
            "confidentiality_period": {"action": "maintain_confidentiality", "anchor": "contract_effective", "timing_type": "continuous"},
            "deliverables": {"action": "deliver", "anchor": "milestone_reached"},
            "cure_periods": {"action": "cure_breach", "anchor": "breach_notice", "timing_type": "deadline"}
        }

        # Bucket 3: Termination & Renewal Rights
        self.TERMINATION_RIGHT_FIELDS = {
            "termination_for_convenience": "terminate",
            "termination_for_cause": "terminate",
            "renewal_terms": "renew",
            "assignment_rights": "assign"
        }

        # Bucket 4: Financial Entities
        self.FINANCIAL_COMMITMENT_FIELDS = {"total_contract_value": "total_contract_value", "payment_terms": "recurring"}
        self.FINANCIAL_CAP_FIELDS = {"liability_cap": "liability"}
        self.FINANCIAL_PENALTY_FIELDS = {"late_fees": "late_payment", "penalties": "sla_breach"}

        # Bucket 7: Operational constraints
        self.OPERATIONAL_OBLIGATION_FIELDS = {
            "confidentiality_period": "maintain",
            "data_protection": "comply",
            "audit_rights": "audit",
            "insurance_requirements": "maintain"
        }

        # Bucket 8: Null-Derived Risks
        self.CRITICAL_MISSING_RISKS = {
            "cure_periods": ("no_cure_period", "medium"),
            "liability_cap": ("uncapped_liability", "critical"),
            "termination_for_convenience": ("no_exit_clause", "high")
        }

        try:
            self.patterns = self._build_comprehensive_patterns()
        except Exception as e:
            logger.error(f"Failed to initialize ContractExtractor: {e}")
            raise

    def cleanup(self):
        logger.info("Performing cleanup...")
        gc.collect()

    def _build_comprehensive_patterns(self) -> Dict[str, PatternConfig]:
        patterns = {}
        patterns_dir = os.path.join(os.path.dirname(__file__), "patterns")

        if not os.path.isdir(patterns_dir):
            return {}

        for filename in os.listdir(patterns_dir):
            if not filename.endswith(".yaml"):
                continue

            key = filename.replace(".yaml", "")
            # Support all fields, not just essential
            if key not in ALL_FIELDS:
                continue

            try:
                with open(os.path.join(patterns_dir, filename), "rb") as f:
                    config_data = msgspec.yaml.decode(f.read(), type=PatternConfig)
                    patterns[key] = config_data
            except Exception as e:
                logger.error("Failed to load pattern file %s: %s", filename, e)

        return patterns

    def _smart_truncate(self, text: str, max_chars: int = 100000) -> Tuple[str, bool]:
        if len(text) <= max_chars:
            logger.info(f"Contract text length: {len(text)} chars (no truncation needed)")
            return text, False

        first_part_size = int(max_chars * 0.6)
        last_part_size = int(max_chars * 0.4)

        truncated = (
            text[:first_part_size]
            + "\n\n[... middle section omitted due to length ...]\n\n"
            + text[-last_part_size:]
        )

        logger.warning(
            f"Contract text truncated from {len(text)} to {len(truncated)} chars "
            f"(first {first_part_size}, last {last_part_size})"
        )

        return truncated, True

    # ═══════════════════════════════════════════════════════════════════════════════
    # SMART CHUNKING FOR LONG CONTRACTS (>50 pages)
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Section markers for intelligent boundary detection
    SECTION_MARKERS = [
        r'^ARTICLE\s+[IVX\d]+\.?',           # ARTICLE I, ARTICLE 1
        r'^SECTION\s+\d+\.?',                 # SECTION 1
        r'^\d+\.\s+[A-Z][A-Z\s]{3,}$',        # 1. DEFINITIONS
        r'^EXHIBIT\s+[A-Z\d]+',               # EXHIBIT A
        r'^SCHEDULE\s+[A-Z\d]+',              # SCHEDULE 1
        r'^APPENDIX\s+[A-Z\d]+',              # APPENDIX A
        r'^ANNEX\s+[A-Z\d]+',                 # ANNEX A
        r'^PART\s+[IVX\d]+',                  # PART I
    ]
    
    def _detect_section_boundaries(self, pages: List[PageText]) -> List[Dict]:
        """
        Detect section boundaries using regex markers.
        
        Returns list of:
            {"page": int, "title": str, "char_offset": int}
        """
        boundaries = []
        compiled_patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in self.SECTION_MARKERS]
        
        total_offset = 0
        for page in pages:
            for pattern in compiled_patterns:
                for match in pattern.finditer(page.text):
                    boundaries.append({
                        "page": page.page_number,
                        "title": match.group().strip(),
                        "char_offset": total_offset + match.start()
                    })
            total_offset += len(page.text) + 2  # +2 for page separator
        
        # Sort by char_offset
        boundaries.sort(key=lambda x: x["char_offset"])
        
        if boundaries:
            logger.info(f"Detected {len(boundaries)} section boundaries")
        
        return boundaries

    def _intelligent_chunk(self, pages: List[PageText], max_tokens: int = 40000) -> List[str]:
        """
        Split long contracts at section boundaries instead of mid-clause.
        
        Args:
            pages: List of PageText objects
            max_tokens: Approximate max tokens per chunk (~4 chars per token)
        
        Returns:
            List of text chunks with overlap at boundaries
        """
        max_chars = max_tokens * 4  # Rough estimate
        
        # Build full text
        full_text = self._format_pages_for_llm(pages)
        
        # If short enough, return as single chunk
        if len(full_text) <= max_chars:
            logger.info("Contract fits in single chunk, no splitting needed")
            return [full_text]
        
        # Detect section boundaries
        boundaries = self._detect_section_boundaries(pages)
        
        # If no boundaries detected, fall back to page-based splitting
        if not boundaries:
            logger.warning("No section boundaries detected, falling back to page-based splitting")
            return self._chunk_by_pages(pages, max_chars)
        
        # Build chunks at section boundaries
        chunks = []
        current_chunk = ""
        overlap_paragraphs = []  # Last 2 paragraphs for context overlap
        
        # Add boundary offsets to full text splitting
        boundary_offsets = [b["char_offset"] for b in boundaries]
        
        prev_offset = 0
        for i, offset in enumerate(boundary_offsets):
            section_text = full_text[prev_offset:offset]
            
            # Check if adding this section would exceed limit
            if len(current_chunk) + len(section_text) > max_chars and current_chunk:
                # Save current chunk with overlap
                if overlap_paragraphs:
                    current_chunk = "\n\n[...context from previous section...]\n" + "\n\n".join(overlap_paragraphs[-2:]) + "\n\n" + current_chunk
                chunks.append(current_chunk)
                
                # Extract overlap from end of current chunk
                paragraphs = current_chunk.split("\n\n")
                overlap_paragraphs = paragraphs[-2:] if len(paragraphs) >= 2 else paragraphs
                
                # Start new chunk
                current_chunk = section_text
            else:
                current_chunk += section_text
            
            prev_offset = offset
        
        # Add remaining text
        remaining = full_text[prev_offset:]
        if current_chunk or remaining:
            final_chunk = current_chunk + remaining
            if overlap_paragraphs and chunks:  # Not the first chunk
                final_chunk = "\n\n[...context from previous section...]\n" + "\n\n".join(overlap_paragraphs[-2:]) + "\n\n" + final_chunk
            chunks.append(final_chunk)
        
        logger.info(f"Split contract into {len(chunks)} chunks at section boundaries")
        return chunks

    def _chunk_by_pages(self, pages: List[PageText], max_chars: int) -> List[str]:
        """Fallback: chunk by page count when no section markers found."""
        chunks = []
        current_chunk = ""
        
        for page in pages:
            page_text = f"Page {page.page_number}:\n{page.text}\n\n"
            
            if len(current_chunk) + len(page_text) > max_chars and current_chunk:
                chunks.append(current_chunk)
                # Keep last page for overlap
                current_chunk = f"[...continuing from page {page.page_number - 1}...]\n\n" + page_text
            else:
                current_chunk += page_text
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"Split contract into {len(chunks)} chunks by page boundaries")
        return chunks

    # ═══════════════════════════════════════════════════════════════════════════════
    # TABLE EXTRACTION (Payment Schedules, Fee Tables)
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Keywords that indicate a payment/fee table
    PAYMENT_TABLE_KEYWORDS = {
        'amount', 'fee', 'price', 'cost', 'payment', 'rate',
        'milestone', 'phase', 'schedule', 'date', 'due',
        'total', 'subtotal', 'invoice', 'billing'
    }

    def _extract_tables(self, doc: fitz.Document) -> List[Dict]:
        """
        Extract tables from PDF using PyMuPDF's built-in table detection.
        
        Returns list of:
            {"page": int, "type": str, "headers": list, "rows": list}
        """
        tables_found = []
        
        for page_idx, page in enumerate(doc, start=1):
            try:
                # PyMuPDF table detection
                tables = page.find_tables()
                
                for table_idx, table in enumerate(tables):
                    # Extract table data
                    data = table.extract()
                    
                    if not data or len(data) < 2:  # Need at least header + 1 row
                        continue
                    
                    headers = data[0] if data else []
                    rows = data[1:] if len(data) > 1 else []
                    
                    # Classify table type
                    table_type = self._classify_table(headers)
                    
                    tables_found.append({
                        "page": page_idx,
                        "table_index": table_idx,
                        "type": table_type,
                        "headers": [h.strip() if h else "" for h in headers],
                        "rows": [[cell.strip() if cell else "" for cell in row] for row in rows]
                    })
                    
                    logger.info(f"Extracted {table_type} table from page {page_idx} ({len(rows)} rows)")
                    
            except Exception as e:
                logger.warning(f"Table extraction failed on page {page_idx}: {e}")
                continue
        
        return tables_found

    def _classify_table(self, headers: List[str]) -> str:
        """
        Classify table type based on header keywords.
        
        Returns: "payment_schedule" | "fee_table" | "party_table" | "generic"
        """
        if not headers:
            return "generic"
        
        header_text = " ".join([h.lower() for h in headers if h])
        
        # Check for payment/fee indicators
        payment_matches = sum(1 for kw in self.PAYMENT_TABLE_KEYWORDS if kw in header_text)
        
        if payment_matches >= 2:
            if any(kw in header_text for kw in ['milestone', 'phase', 'schedule']):
                return "payment_schedule"
            return "fee_table"
        
        if any(kw in header_text for kw in ['party', 'name', 'entity', 'signatory']):
            return "party_table"
        
        return "generic"

    def _format_tables_for_llm(self, tables: List[Dict]) -> str:
        """
        Format extracted tables as structured text for LLM context.
        
        Only includes payment_schedule and fee_table types.
        """
        if not tables:
            return ""
        
        relevant_tables = [t for t in tables if t["type"] in ("payment_schedule", "fee_table")]
        
        if not relevant_tables:
            return ""
        
        formatted_parts = ["\n\n═══ EXTRACTED PAYMENT/FEE TABLES ═══\n"]
        
        for table in relevant_tables:
            formatted_parts.append(f"\n[{table['type'].upper()} - Page {table['page']}]")
            
            # Format as simple table
            headers = table["headers"]
            formatted_parts.append(" | ".join(headers))
            formatted_parts.append("-" * 40)
            
            for row in table["rows"][:20]:  # Limit to 20 rows
                formatted_parts.append(" | ".join(row))
            
            if len(table["rows"]) > 20:
                formatted_parts.append(f"... and {len(table['rows']) - 20} more rows")
        
        return "\n".join(formatted_parts)

    def _normalize_payment_schedule(self, tables: List[Dict]) -> List[Dict]:
        """
        Normalize payment schedule tables into structured format with escalation detection.
        """
        normalized = []
        
        for table in tables:
            if table["type"] not in ("payment_schedule", "fee_table"):
                continue
            
            headers = [h.lower() for h in table["headers"]]
            
            # Find column indices for structured schedule fields
            period_col = next((i for i, h in enumerate(headers) if any(kw in h for kw in ['period', 'year', 'term'])), None)
            base_annual_col = next((i for i, h in enumerate(headers) if ('base' in h and 'annual' in h) or ('annual' in h and 'fee' in h)), None)
            effective_annual_col = next((i for i, h in enumerate(headers) if ('effective' in h and 'annual' in h) or ('effective' in h and 'rate' in h)), None)
            escalation_col = next((i for i, h in enumerate(headers) if any(kw in h for kw in ['escalation', 'cpi', 'increase', 'rate %', 'rate'])), None)

            # Fallbacks
            amount_col = next((i for i, h in enumerate(headers) if any(kw in h for kw in ['amount', 'fee', 'price', 'cost', 'payment'])), None)
            date_col = next((i for i, h in enumerate(headers) if any(kw in h for kw in ['date', 'due', 'when'])), None)
            milestone_col = next((i for i, h in enumerate(headers) if any(kw in h for kw in ['milestone', 'phase', 'deliverable', 'description', 'item'])), None)

            def _parse_money(value: str) -> Optional[float]:
                return parse_currency(value)

            def _parse_rate(value: str) -> Optional[float]:
                if not value: return None
                pct = re.search(r'(\d+(?:\.\d+)?)\s*%', value)
                if pct: return float(pct.group(1)) / 100.0
                return None

            def _extract_year_bounds(period_text: str) -> Tuple[Optional[str], Optional[str]]:
                if not period_text: return None, None
                years = re.findall(r'\b(20\d{2})\b', period_text)
                if not years: return None, None
                start_year = int(years[0])
                end_year = int(years[-1])
                return f"{start_year:04d}-01-01", f"{end_year:04d}-12-31"
            
            for row in table["rows"]:
                period_val = row[period_col] if period_col is not None and period_col < len(row) else ""
                start_date, end_date = _extract_year_bounds(period_val)

                effective_annual = _parse_money(row[effective_annual_col]) if effective_annual_col is not None and effective_annual_col < len(row) else None
                if effective_annual is None and amount_col is not None and amount_col < len(row):
                    effective_annual = _parse_money(row[amount_col])
                
                escalation_rate = _parse_rate(row[escalation_col]) if escalation_col is not None and escalation_col < len(row) else None

                entry = {
                    "description": row[milestone_col] if milestone_col is not None and milestone_col < len(row) else "Fee",
                    "amount": effective_annual,
                    "date": row[date_col] if date_col is not None and date_col < len(row) else start_date,
                    "start_date": start_date,
                    "end_date": end_date,
                    "escalation_rate": escalation_rate,
                    "type": "recurring" if start_date or escalation_rate else "fixed",
                    "page": table["page"]
                }
                normalized.append(entry)
        
        if normalized:
            logger.info(f"Normalized {len(normalized)} payment schedule entries")
        
        return normalized

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * INPUT_TOKEN_COST) + (output_tokens * OUTPUT_TOKEN_COST)

    @retry(
        retry=retry_if_exception_type((APIError, RateLimitError, Exception)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _call_claude_with_retry(self, messages, system_prompt, max_tokens):
        """
        Call Claude API with retry logic.

        🔒 FIX: Added 30-second timeout to prevent hanging requests
        """
        if not self.client:
            raise ValueError("Anthropic client not initialized")

        logger.info("Calling Claude API...")

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                system=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0,
                timeout=60.0  # Increased timeout for larger extractions
            )
            return response

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise

    def _find_visual_coordinates(self, doc: fitz.Document, page_num: int, text_to_find: str) -> List[List[float]]:
        """
        Searches the actual PDF page for the visual coordinates of the text.
        Returns a list of [x0, y0, x1, y1] rects.
        """
        if not text_to_find or not page_num or page_num < 1 or page_num > doc.page_count:
            return []

        try:
            page = doc[page_num - 1]  # 0-indexed in fitz

            # Clean the search text
            clean_search = " ".join(text_to_find.split())

            # Try exact match
            rects = page.search_for(clean_search)

            # If no match, try shorter snippet
            if not rects and len(clean_search) > 30:
                short_snippet = clean_search[:30]
                rects = page.search_for(short_snippet)

                if not rects:
                    mid = len(clean_search) // 2
                    mid_snippet = clean_search[mid:mid+30]
                    rects = page.search_for(mid_snippet)

            bbox_list = [[r.x0, r.y0, r.x1, r.y1] for r in rects]
            return bbox_list

        except Exception as e:
            logger.warning(f"Error searching for coordinates on page {page_num}: {e}")
            return []

    def _validate_and_fill_gaps(self, initial_results: Dict, pages: List[PageText], target_fields: set) -> Dict:
        """
        Pass 2: Self-correction and gap-filling.
        
        Reviews fields that returned "Not Found" or have suspicious values, 
        OR fields whose verbatim snippets failed grounding verification (Hallucination Guard).
        """
        if not self.client:
            return initial_results
        
        full_text = self._format_pages_for_llm(pages)
        fields_to_recheck = []
        
        for field in target_fields:
            result = initial_results.get(field, {})
            value = result.get("value")
            quote = result.get("verbatim_source")
            
            needs_recheck = False
            
            # Condition 1: Missing or Suspicious
            if value is None or value == "null" or value == "Not Found":
                needs_recheck = True
                logger.info(f"Pass 2: Re-checking '{field}' (Gap found)")
            elif isinstance(value, str) and len(value.strip()) < 3 and field != "currency":
                needs_recheck = True
                logger.info(f"Pass 2: Re-checking '{field}' (Suspiciously short)")
            
            # Condition 2: Hallucination Guard (Snippet verification)
            if not needs_recheck and quote and quote != "null":
                if not fuzzy_text_exists(quote, full_text):
                    needs_recheck = True
                    logger.warning(f"Pass 2: Re-checking '{field}' (Grounding failure/Potential hallucination)")
            
            if needs_recheck:
                fields_to_recheck.append(field)
        
        if not fields_to_recheck:
            logger.info("Pass 2: All fields verified, skipping re-check")
            return initial_results
        
        logger.info(f"Pass 2: Re-analyzing {len(fields_to_recheck)} fields due to gaps or grounding failures")
        
        # Build focused re-extraction prompt
        field_descriptions_text = "\n".join([
            f"- {field}: {FIELD_DESCRIPTIONS.get(field, field)}"
            for field in fields_to_recheck
        ])
        
        recheck_prompt_template = os.getenv("CLAUDE_RECHECK_PROMPT", DEFAULT_RECHECK_PROMPT)
        recheck_prompt = f"{recheck_prompt_template}\n\nFIELDS TO RE-EXTRACT:\n{field_descriptions_text}\n\nNOTE: For fields previously extracted, your previous answer was suspicious or the quote provided was NOT found in the text. Look closer and provide an EXACT verbatim quote."
        
        # Format text for LLM
        truncated_text, _ = self._smart_truncate(full_text, 80000)
        messages = [{"role": "user", "content": f"Re-analyze this contract for the missing or failed fields:\n\n{truncated_text}"}]
        
        try:
            response = self._call_claude_with_retry(
                messages,
                system_prompt=recheck_prompt,
                max_tokens=2000
            )
            
            content_text = response.content[0].text
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
            if json_match:
                recheck_data = json.loads(json_match.group(0))
            else:
                recheck_data = json.loads(content_text)
            
            # Merge results - only update if new value is better
            updated_results = initial_results.copy()
            fixes_applied = 0
            
            for field, new_result in recheck_data.items():
                if field not in fields_to_recheck:
                    continue
                    
                new_value = new_result.get("value")
                if new_value and new_value != "null" and new_value != "Not Found":
                    updated_results[field] = new_result
                    fixes_applied += 1
            
            logger.info(f"Pass 2 complete: {fixes_applied}/{len(fields_to_recheck)} fields fixed or grounded.")
            return updated_results
            
        except Exception as e:
            logger.warning(f"Pass 2 failed, continuing with initial results: {e}")
            return initial_results


    def _build_schema_prompt(self, target_fields: set, label: str = "custom") -> str:
        """Build the extraction prompt based on target fields.
        
        Args:
            target_fields: Set of field names to extract
            label: Label for logging (e.g., 'default', 'custom')
        """
        fields = target_fields
        
        # Group fields by category for better organization
        categories = {
            "CORE DATES & PARTIES": ["effective_date", "expiration_date", "parties"],
            "FINANCIAL TERMS": ["total_contract_value", "payment_terms", "currency"],
            "TERMINATION & RENEWAL": ["termination_notice_period", "renewal_terms", "governing_law"],
            "LIABILITY & RISK": ["liability_cap", "indemnification_clauses", "insurance_requirements", "limitation_of_liability"],
            "PERFORMANCE & OBLIGATIONS": ["deliverables", "sla_terms", "performance_metrics", "acceptance_criteria"],
            "INTELLECTUAL PROPERTY": ["ip_ownership", "license_scope", "usage_restrictions"],
            "COMPLIANCE & DISPUTE": ["confidentiality_period", "non_compete_terms", "arbitration_clause", "audit_rights", "data_protection"],
            "ADMINISTRATIVE": ["notice_address", "amendment_process", "assignment_rights", "force_majeure"],
            # NEW EXTENDED CATEGORIES
            "PAYMENT WORKFLOW": ["late_fees", "payment_milestones", "invoice_frequency", "dispute_procedures", "escrow_terms"],
            "COMPLIANCE EXTENDED": ["gdpr_obligations", "ccpa_compliance", "security_standards", "audit_frequency", "certification_requirements"],
            "PERFORMANCE EXTENDED": ["penalties", "cure_periods", "escalation_procedures", "change_order_process", "warranty_terms"],
            "RISK MANAGEMENT": ["risk_allocation", "contingency_provisions", "material_breach_definition", "remedies"],
            "TERMINATION EXTENDED": ["termination_for_cause", "termination_for_convenience", "transition_assistance", "survival_clauses"],
            "IP EXTENDED": ["background_ip", "foreground_ip", "joint_ip", "moral_rights_waiver", "source_code_escrow"],
            "COMMERCIAL TERMS": ["exclusivity", "territory_restrictions", "volume_commitments", "price_adjustments", "benchmarking_rights"],
            "RELATIONSHIP TERMS": ["subcontracting_rights", "key_personnel", "governance_structure", "reporting_requirements"],
        }
        
        # Build field list for prompt
        field_sections = []
        field_count = 0
        
        for category_name, category_fields in categories.items():
            active_fields = [f for f in category_fields if f in fields]
            if active_fields:
                section = f"\n═══ {category_name} ═══"
                for field in active_fields:
                    field_count += 1
                    description = FIELD_DESCRIPTIONS.get(field, field)
                    
                    # Add facet requirements to description
                    facets = get_applicable_facets(field)
                    facet_instr = ""
                    if facets:
                        facet_instr = f" (Also determine facets: {', '.join(facets)})"
                        
                    section += f"\n{field_count}. {field}\n   - {description}{facet_instr}"
                field_sections.append(section)
        
        fields_list = "\n".join(field_sections)
        
        # Get prompt from environment or use default
        prompt_template = os.getenv("CLAUDE_EXTRACTION_PROMPT", DEFAULT_EXTRACTION_PROMPT)
        
        # Simple formatting if the template expects it
        try:
             # Check if the template has the formatting keys we expect
             if "{fields_list}" in prompt_template:
                 return prompt_template.format(fields_list=fields_list, label=label.upper())
             else:
                 return f"{prompt_template}\n\nFIELDS TO EXTRACT:\n{fields_list}"
        except Exception:
             return f"{prompt_template}\n\nFIELDS TO EXTRACT:\n{fields_list}"

    def _extract_all_fields_with_llm(self, pages: List[PageText], target_fields: set, label: str = "custom", table_context: str = "") -> Dict[str, Dict[str, Any]]:
        if not self.client:
            logger.warning("No API key available for LLM extraction.")
            return {}

        full_contract_text = self._format_pages_for_llm(pages)
        logger.info(f"Formatted {len(pages)} pages into {len(full_contract_text)} chars for LLM")

        # Adjust truncation based on field count (more fields need more context)
        field_count = len(target_fields)
        if field_count <= 9:
            max_chars = 100000
        elif field_count <= 18:
            max_chars = 125000
        else:
            max_chars = 150000
        
        truncated_text, was_truncated = self._smart_truncate(full_contract_text, max_chars)
        
        # Append table context if we have it (helps with financial field extraction)
        if table_context:
            truncated_text = truncated_text + table_context
            logger.info(f"Added {len(table_context)} chars of table context to LLM input")

        # Build prompt with target fields
        schema_prompt = self._build_schema_prompt(target_fields, label)

        messages = [
            {"role": "user", "content": f"Analyze this contract text:\n\n{truncated_text}"}
        ]

        # Max tokens for all tiers - 25 fields × ~150 tokens = ~4000 output tokens
        # Using 4500 to provide headroom for all extraction tiers (max 25 fields)
        max_tokens = 4500

        try:
            logger.info(f"Sending request to Claude for {label} extraction ({len(target_fields)} fields)...")
            response = self._call_claude_with_retry(
                messages,
                system_prompt=schema_prompt,
                max_tokens=max_tokens
            )

            # 🔒 FIX: Log cost and alert if high
            if hasattr(response, "usage"):
                cost = self._calculate_cost(
                    response.usage.input_tokens,
                    response.usage.output_tokens
                )

                logger.info(
                    f"LLM Usage: {response.usage.input_tokens} input tokens, "
                    f"{response.usage.output_tokens} output tokens, "
                    f"cost=${cost:.6f}"
                )

                # 🔒 FIX: Cost monitoring alert
                if cost > HIGH_COST_ALERT_THRESHOLD:
                    logger.critical(f"🚨 HIGH COST ALERT: ${cost:.4f} for this extraction")

            content_text = response.content[0].text

            # Extract JSON from potential Markdown blocks
            json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
            else:
                data = json.loads(content_text)

            logger.info("Successfully parsed JSON from LLM response")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"LLM Extraction failed: {e}", exc_info=True)
            return {}

    def _extract_from_chunks(self, chunks: List[str], target_fields: set, label: str = "custom", table_context: str = "") -> Dict[str, Dict[str, Any]]:
        """
        Extract from multiple chunks and merge results.
        
        For long contracts (>50 pages), we extract from each chunk and merge,
        preferring non-null values from any chunk.
        """
        logger.info(f"Multi-chunk extraction: {len(chunks)} chunks")
        
        # Add table context to first chunk only (it's the most relevant)
        chunk_with_tables = chunks[0] + table_context if table_context else chunks[0]
        modified_chunks = [chunk_with_tables] + chunks[1:]
        
        all_results = []
        
        for i, chunk in enumerate(modified_chunks):
            logger.info(f"Processing chunk {i + 1}/{len(modified_chunks)} ({len(chunk)} chars)")
            
            chunk_result = self._extract_from_text_chunk(chunk, target_fields, label)
            if chunk_result:
                all_results.append(chunk_result)
        
        # Merge results: prefer non-null values
        return self._merge_chunk_results(all_results, target_fields)

    def _extract_from_text_chunk(self, text: str, target_fields: set, label: str = "custom") -> Dict[str, Dict[str, Any]]:
        """Extract fields from a single text chunk."""
        if not self.client:
            return {}
        
        truncated, _ = self._smart_truncate(text, 100000)
        schema_prompt = self._build_schema_prompt(target_fields, label)
        
        messages = [
            {"role": "user", "content": f"Analyze this contract text:\n\n{truncated}"}
        ]
        
        try:
            response = self._call_claude_with_retry(
                messages,
                system_prompt=schema_prompt,
                max_tokens=4500
            )
            
            content_text = response.content[0].text
            
            json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                return json.loads(content_text)
                
        except Exception as e:
            logger.warning(f"Chunk extraction failed: {e}")
            return {}

    def _merge_chunk_results(self, results_list: List[Dict], target_fields: set) -> Dict[str, Dict[str, Any]]:
        """
        Merge extraction results from multiple chunks.
        
        Strategy: For each field, take the first non-null value found.
        This prefers earlier chunks (which usually have the key terms).
        """
        merged = {}
        
        for field in target_fields:
            # Try each result until we find a non-null value
            for result in results_list:
                if field in result:
                    value = result[field].get("value") if isinstance(result[field], dict) else result[field]
                    if value and value != "null" and value != "Not Found":
                        merged[field] = result[field]
                        break
            
            # If still not found, use the first result's value (even if null)
            if field not in merged:
                for result in results_list:
                    if field in result:
                        merged[field] = result[field]
                        break
        
        logger.info(f"Merged {len(merged)} fields from {len(results_list)} chunks")
        return merged

    # ═══════════════════════════════════════════════════════════════════════════════
    # OBJECT DERIVATION (The Knowledge Graph)
    # ═══════════════════════════════════════════════════════════════════════════════

    def derive_objects(self, analysis: Dict) -> Dict:
        """Pattern-based routing of flat fields into structured actionable objects."""
        objects = {
            "obligations": [], "rights": [], "risks": [],
            "financial_commitments": [], "financial_caps": [], "financial_penalties": []
        }
        
        for field_name, field_data in analysis.items():
            if not isinstance(field_data, dict): continue
            value = field_data.get("value")
            if not value or value in ("Not Found", "null"): continue
            
            # Routing logic
            if field_name in self.TIME_BOUND_OBLIGATION_FIELDS:
                objects["obligations"].extend(self.derive_time_obligation(field_name, field_data))
                
            elif field_name in self.TERMINATION_RIGHT_FIELDS:
                rights, risks = self.derive_termination_right(field_name, field_data)
                objects["rights"].extend(rights)
                objects["risks"].extend(risks)
                
            elif field_name in self.FINANCIAL_COMMITMENT_FIELDS:
                objects["financial_commitments"].extend(self.derive_financial_commitment(field_name, field_data))
                
            elif field_name in self.FINANCIAL_CAP_FIELDS:
                caps, risks = self.derive_financial_cap(field_name, field_data)
                objects["financial_caps"].extend(caps)
                objects["risks"].extend(risks)
                
            elif field_name in self.FINANCIAL_PENALTY_FIELDS:
                objects["financial_penalties"].extend(self.derive_financial_penalty(field_name, field_data))
                
            elif field_name in self.OPERATIONAL_OBLIGATION_FIELDS:
                objects["obligations"].extend(self.derive_operational_obligation(field_name, field_data))
        
        # Null-Derived Risks (The 'Secret Sauce')
        objects["risks"].extend(self.derive_missing_field_risks(analysis))
        return objects

    def derive_time_obligation(self, field_name: str, field_data: Dict) -> List[Dict]:
        config = self.TIME_BOUND_OBLIGATION_FIELDS[field_name]
        facets = field_data.get("facets", {})
        obligation = {
            "id": f"obl_{field_name}_{stable_hash(field_data['value'])}",
            "type": "obligation",
            "action": config["action"],
            "description": summarize_value(field_data["value"]),
            "timing": {"anchor": config["anchor"], "offset_days": parse_days_from_text(field_data["value"])},
            "source_fields": [field_name],
            "mutual": facets.get("mutual", False)
        }
        return [obligation]

    def derive_termination_right(self, field_name: str, field_data: Dict) -> Tuple[List[Dict], List[Dict]]:
        action = self.TERMINATION_RIGHT_FIELDS[field_name]
        facets = field_data.get("facets", {})
        holder = "seller" if facets.get("favors") == "seller" else "buyer"
        right = {
            "id": f"right_{action}_{holder}_{stable_hash(field_data['value'])}",
            "type": "right",
            "holder": holder,
            "action": action,
            "description": summarize_value(field_data["value"]),
            "source_fields": [field_name]
        }
        risks = []
        if not facets.get("mutual"):
            risks.append({
                "type": "risk", "risk_type": "asymmetric_right", "severity": "medium",
                "description": f"{field_name} favors {facets.get('favors', 'one')} party"
            })
        return [right], risks

    def derive_financial_commitment(self, field_name: str, field_data: Dict) -> List[Dict]:
        return [{
            "type": "financial_commitment",
            "amount": parse_currency(field_data["value"]),
            "currency": extract_currency(field_data["value"]),
            "structure": infer_payment_structure(field_name, field_data["value"])
        }]

    def derive_financial_cap(self, field_name: str, field_data: Dict) -> Tuple[List[Dict], List[Dict]]:
        val = field_data["value"]
        facets = field_data.get("facets", {})
        amount = parse_currency(val)
        if not amount:
            return [], [{"type": "risk", "risk_type": "uncapped_liability", "severity": "critical", "description": "No financial cap found"}]
        cap = {"type": "financial_cap", "amount": amount, "currency": extract_currency(val), "mutual": facets.get("mutual", False)}
        return [cap], []

    def derive_financial_penalty(self, field_name: str, field_data: Dict) -> List[Dict]:
        return [{"type": "financial_penalty", "calculation": parse_penalty_calculation(field_data["value"]), "triggered_by": link_to_obligation(field_name)}]

    def derive_operational_obligation(self, field_name: str, field_data: Dict) -> List[Dict]:
        return [{"type": "obligation", "action": self.OPERATIONAL_OBLIGATION_FIELDS[field_name], "description": summarize_value(field_data["value"])}]

    def derive_missing_field_risks(self, analysis: Dict) -> List[Dict]:
        risks = []
        for field, (risk_type, severity) in self.CRITICAL_MISSING_RISKS.items():
            if field not in analysis or analysis[field]["value"] in ("Not Found", "null"):
                risks.append({"type": "risk", "risk_type": risk_type, "severity": severity, "description": generate_risk_description(risk_type, {})})
        return risks

    def _format_pages_for_llm(self, pages: List[PageText]) -> str:
        parts = []
        for page in pages:
            parts.append(f"Page {page.page_number}:\n{page.text}")
        return "\n\n".join(parts)

    def _extract_text_from_pdf(self, doc: fitz.Document) -> List[PageText]:
        pages: List[PageText] = []
        logger.info("Processing %d pages from PDF.", doc.page_count)

        for page_index, page in enumerate(doc, start=1):
            text_content = ""
            try:
                text_content = page.get_text("text")
            except Exception as e:
                logger.warning("Could not extract text from page %d: %s", page_index, e)

            pages.append(PageText(page_number=page_index, text=text_content))

        return pages

    def extract_from_pdf(self, pdf_file: Union[bytes, io.BytesIO], fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Deprecated: Use extract_from_file instead."""
        return self.extract_from_file(pdf_file, extension="pdf", fields=fields)

    @performance_profiler
    def extract_from_file(
        self, 
        file_input: Union[bytes, io.BytesIO], 
        extension: str = "pdf",
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract contract data from PDF or DOCX.
        
        Args:
            file_input: File as bytes or BytesIO
            extension: 'pdf' or 'docx'
            fields: Optional list of field names to extract. Defaults to internal DEFAULT_FIELDS.
        """
        # Determine target fields
        if fields:
            valid_fields = set(fields) & ALL_FIELDS
            target_fields = valid_fields if valid_fields else DEFAULT_FIELDS
            logger.info(f"Starting {extension.upper()} extraction pipeline - CUSTOM ({len(target_fields)} fields)")
        else:
            target_fields = DEFAULT_FIELDS
            logger.info(f"Starting {extension.upper()} extraction pipeline - DEFAULT ({len(target_fields)} fields)")

        doc = None
        try:
            file_stream = io.BytesIO(file_input) if isinstance(file_input, bytes) else file_input
            
            if extension.lower() == "pdf":
                doc = fitz.open(stream=file_stream, filetype="pdf")
                if doc.is_encrypted: return {"error": "PDF is encrypted."}
                page_texts = self._extract_text_from_pdf(doc)
                extracted_tables = self._extract_tables(doc)
            elif extension.lower() == "docx":
                if not DOCX_AVAILABLE: return {"error": "python-docx not installed."}
                doc = DocxDocument(file_stream)
                page_texts = self._extract_text_from_docx(doc)
                extracted_tables = self._extract_tables_from_docx(doc)
            else:
                return {"error": f"Unsupported extension: {extension}"}

            if not any(p.text.strip() for p in page_texts):
                return {"error": "No text content found."}

            page_count = len(page_texts)
            table_context = self._format_tables_for_llm(extracted_tables)
            normalized_payments = self._normalize_payment_schedule(extracted_tables)
            
            # Smart Chunking
            chunks = self._intelligent_chunk(page_texts) if page_count > 50 else None
            
            # Pass 1 & 2
            field_label = "custom" if fields else "default"
            if chunks and len(chunks) > 1:
                llm_results = self._extract_from_chunks(chunks, target_fields, field_label, table_context)
            else:
                llm_results = self._extract_all_fields_with_llm(page_texts, target_fields, field_label, table_context)

            validated_results = self._validate_and_fill_gaps(llm_results, page_texts, target_fields)

            # Pass 3: Grounding & Honesty
            analysis: Dict[str, Dict[str, Any]] = {}
            grounded_count = 0
            full_text = " ".join([p.text for p in page_texts])

            for key in target_fields:
                item = validated_results.get(key, {})
                val, quote, pg = item.get("value"), item.get("verbatim_source"), item.get("page_number")
                
                grounded = False
                snippet = None
                bboxes = None

                if val and val not in ("null", "Not Found"):
                    if extension.lower() == "pdf" and pg and quote:
                        bboxes = self._find_visual_coordinates(doc, pg, quote)
                        if bboxes: 
                            grounded = True
                            snippet = quote
                    
                    if not grounded and quote and fuzzy_text_exists(quote, full_text):
                        grounded = True
                        snippet = quote
                    
                    if grounded: grounded_count += 1

                # Extract facets
                facets = {f: item[f] for f in get_applicable_facets(key) if f in item}

                # Build result object
                result_obj = ExtractionResult(
                    value=val if val is not None else "Not specified",
                    source=ExtractionSource.LLM if val and val != "null" else ExtractionSource.SYSTEM_FALLBACK,
                    page_number=pg,
                    reference_snippet=snippet,
                    bbox=bboxes,
                    grounded=grounded,
                    facets=facets if facets else None,
                    confidence_score=0.98 if grounded else (0.7 if val and val != "null" else 0.0)
                )
                analysis[key] = result_obj.to_dict()

            analysis = normalize_analysis_payload(analysis)
            legal_objects = self.derive_objects(analysis)
            
            return {
                "extraction_timestamp": datetime.now().isoformat(),
                "metadata": {
                    "document_format": extension.upper(),
                    "document_complexity": compute_document_complexity(analysis),
                    "grounding_rate": f"{(grounded_count / len(target_fields) * 100):.1f}%" if target_fields else "0%",
                    "knowledge_graph": legal_objects,
                    "pages_processed": page_count,
                    "segments_found": len(extracted_tables),
                    "structured_data": normalized_payments,
                },
                "analysis": analysis
            }

        except Exception as e:
            logger.error(f"Extraction failed: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            if doc and hasattr(doc, "close"): doc.close()

    def cleanup(self):
        """Clean up resources."""
        gc.collect()

# -------------------------------------------------------------------------
# CLI Entry Point
# -------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Contract Extractor")
    parser.add_argument("file", help="Path to PDF or DOCX file")
    parser.add_argument("--fields", help="Comma-separated list of custom fields to extract")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File {args.file} not found.")
        exit(1)
        
    custom_fields = args.fields.split(",") if args.fields else None
        
    extractor = ContractExtractor()
    with open(args.file, "rb") as f:
        ext = os.path.splitext(args.file)[1][1:].lower()
        result = extractor.extract_from_file(f.read(), extension=ext, fields=custom_fields)
        print(json.dumps(result, indent=2))
