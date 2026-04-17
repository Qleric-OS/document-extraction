# Document Extractor V1

![Open Source](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)
![Format](https://img.shields.io/badge/Supports-PDF%20%7C%20DOCX-green.svg)

A production-grade utility for extracting structured data from PDF and DOCX documents. This engine features built-in verification, structural derivation, and multi-format support.

<p align="center">
  <img src="extract1.png" width="30%" />
  <img src="extract2.png" width="30%" />
  <img src="extract3.png" width="30%" />
</p>

## 🚀 Roll Out Strategy

This tool is designed to be dropped into a production environment within 5 minutes.

### 1. Direct Python Integration (The Core Engine)
Perfect for CLI tools, document batch processors, or internal data science pipelines.

```bash
pip install pymupdf python-docx anthropic msgspec spacy
python -m spacy download en_core_web_sm
```

```python
from contract_extractor import ContractExtractor

extractor = ContractExtractor()
with open("contract.pdf", "rb") as f:
    # Full analysis (Bias Detection + Verification + Knowledge Graph)
    result = extractor.extract_from_file(f.read(), extension="pdf")

print(result["metadata"]["knowledge_graph"]) # Access rights and obligations directly
```

### 2. Microservice Deployment (API Strategy)
Deploy as a stateless extraction microservice. A `simple_api.py` is included for rapid rollout.

```bash
# Start the API server
python simple_api.py
```

```bash
# Analyze from any language/environment
curl -X POST -F "file=@legal_agreement.docx" http://localhost:5000/analyze
```

### 3. Enterprise Intelligence (The Business Layer)
Leverage the **Knowledge Graph** and **Verification Logic** to build custom dashboards:
- **Risk Dashboards**: Trigger alerts on "Null-Derived Risks".
- **Visual Timelines**: Map the `obligations` array to a Gantt chart.
- **Audit Trails**: Use the `reference_snippet` and `bbox` (coordinates) to build a clickable side-by-side audit viewer.

## 🧠 Core Intelligence Layers

- **The Bias Detection Logic**: Identifies clause bias (Buyer/Seller favorability) using Field Facets.
- **The Verification Logic**: Mandatory Python-level grounding verification (Hallucination Guard) for every extracted quote.
- **The Object Derivation Engine**: Automatically converts flat keys into Rights, Obligations, and Risks.
- **Multi-Format Structural Intelligence**: Treats DOCX headings as virtual pages for consistent downstream processing.

## 🛠 Setup & Security

1. **API Key**: Add your `ANTHROPIC_API_KEY` to a `.env` file.
2. **Environment**: Recommended Python 3.9+.
3. **Data Privacy**: Documents are processed via Anthropic's API. Ensure your use case complies with your data sovereignty requirements.

## ⚖️ License & Open Source

This repository is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. 

### Why open source?
We provide this core engine to the community to drive the adoption of "Verified Document Intelligence." By making our grounding and derivation logic public, we aim to eliminate "Black Box" extraction in legal-tech.

For commercial support, high-scale managed infrastructure, or the full SaaS suite, visit [qleric.com](https://qleric.com).
