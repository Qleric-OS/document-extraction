"""PII pack: find-and-highlight personal data. Fully local, no key, no LLM.

Every hit returns all spans (not just the best) so annotate() can redact or
highlight each occurrence. The value is the count; verbatim holds each match.

Order matters: phone runs last and skips spans already claimed by ssn/card/iban.
"""
from __future__ import annotations

import re

PATTERNS = [
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("ssn", r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b"),
    ("credit_card", r"\b(?:[0-9][\s-]?){13,19}\b"),
    ("iban", r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b"),
    ("phone", r"\+?[0-9][0-9\s\-().]{6,}[0-9]"),
]

EXCLUDE = {"phone": {"ssn", "credit_card", "iban"}}

FIELDS = [
    {"name": name, "strategy": "pii", "hint": f"all {name} occurrences",
     "pattern": pattern}
    for name, pattern in PATTERNS
]
