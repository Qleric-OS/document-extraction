# Document Extractor V1 - Product Guide

This guide outlines the capabilities of the **Document Extractor V1**

## The Five Layers

The extractor transforms flat text into a high-fidelity "Legal Knowledge Graph" through five distinct layers of processing.

### 1. The Bias Detection Logic (Bias Detection)
Unlike basic extractors that simply return text, our engine acts as a neutral referee. It identifies the **bias** of every clause using the `facets` system.
- **Favors**: Identifies if a clause favors the Buyer, Seller, or is Mutual.
- **Conditionality**: Flags if a right or obligation is contingent on certain events.
- **Mutual Verification**: Automatically detects if rights (like Termination) are asymmetric.

### 2. The Verification Logic (Trust Engineering)
We tackle the "Hallucination Problem" head-on.
- **Hallucination Guard**: Every quote provided by the LLM is verified via Python against the raw text. If it's not there, it's flagged and re-extracted.
- **Source Resolution**: Fields are explicitly marked as `EXTRACTED` (citation available), `INFERRED` (synthesized logic), or `DEFAULT` (system fallback).
- **Confidence Scoring**: Dynamic 0.0–1.0 scores based on grounding strength.

### 3. The Object Derivation Engine (The Knowledge Graph)
The engine routes flat JSON fields into structured **Actionable Objects**:
- **Obligations**: Actionable items with anchors (e.g., "Pay in 30 days").
- **Rights**: Strategic powers (e.g., "Right to Terminate for Convenience").
- **Null-Derived Risks**: Automatically generates risk objects if critical fields (like Liability Caps) are missing.

### 4. Production-Grade Finance
Built for portfolio analytics.
- **Locale Awareness**: Handles US ($1,000.00) vs EU (1.000,00) formats.
- **Escalation Logic**: Detects annual CPI increases, percentage hikes, and fee schedules.
- **Normalizer**: Standardizes financial commits across hundreds of documents.

### 5. Multi-Format Structural Intelligence
- **Native PDF & Word**: Handles both formats with high fidelity.
- **Virtual Page System**: DOCX sections and headings are treated as "pages" to maintain a consistent API for your frontend.

---

## 💼 Business Opportunities
This tool is a complete foundation for several document intelligence businesses:

1. **Portfolio Health Dashboards**: Extract and visualize risk across 1,000s of contracts for M&A due diligence.
2. **Automated Billing Verification**: Use the Financial Normalizer to verify that invoices match contract fee schedules.
3. **Knowledge Graph Visualizers**: Use the `legal_graph` output to build interactive timeline and relationship graphs for legal teams.
4. **Supply Chain Risk Tools**: Use "Null-Derived Risks" to flag non-compliant vendors in seconds.

## 🛠 Technical Specifications

### Unified Extraction
- **Default Fields**: The engine extracts 25 core legal and financial fields by default (including Dates, Parties, Liability Caps, and Termination).
- **Custom Analysis**: Developers can pass a custom list of fields from our 60+ field bank to tailor the analysis to their specific domain.

### Output Structure
```json
{
  "metadata": {
    "grounding_rate": "95.2%",
    "document_complexity": "High (Structured)",
    "knowledge_graph": {
        "obligations": [...],
        "rights": [...],
        "risks": [...]
    }
  },
  "analysis": {
    "effective_date": {
      "value": "2024-01-01",
      "grounded": true,
      "confidence": 0.98,
      "resolution": { "source": "extracted" }
    }
  }
}
```

---


