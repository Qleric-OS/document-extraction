# qleric

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Format](https://img.shields.io/badge/Supports-PDF%20%7C%20DOCX-green.svg)

Grounded document extraction. Every value ships with its **verbatim quote + page + bbox** — no black-box JSON.

## 30 seconds

```bash
pip install -r requirements.txt
python api.py
curl -X POST -F "file=@invoice.pdf" -F "pack=invoice" http://localhost:5000/analyze
```

```json
{
  "fields": {
    "total_amount": {
      "value": "$1,240.00", "verbatim": "Total Due $1,240.00",
      "page_number": 1, "bbox": [[x0, y0, x1, y1]],
      "grounded": true, "source": "regex"
    }
  },
  "meta": {"format": "PDF", "pages": 1, "grounding_rate": "4/8"}
}
```
## Packs (`-F "pack=<name>"`)

| pack | local (offline) | llm (needs key) | pii sweep |
|---|---|---|---|
| `invoice` | number, dates, totals, tax | seller, buyer, line_items | — |
| `resume` | email, phone, experience §, education § | name, skills, current_title | — |
| `pii` | — | — | email, phone, ssn, credit_card, iban (all occurrences + `bboxes` per hit, redaction-ready) |

Add `-F "deep=true"` to force LLM over all unmatched fields, `-F "annotate=true"` for a base64 highlighted PDF.

Python: `from qleric import parse, query; query(parse(data, "pdf"), INVOICE_FIELDS)`.
| **BYOK** | `API_KEY` + `MODEL` (+ `BASE_URL`) | LLM fields via any OpenAI-compatible endpoint — Anthropic, OpenAI, Gemini, Ollama |
| **MCP** | none in our process | point your own assistant at docs: `python -m qleric.mcp` exposes `read_pages`, `find_quote`, `annotate` |

No hosted key, no vendor SDK, single LLM pass with local verification.

## Packs

- `invoice` — numbers, dates, totals, seller/buyer, line items, tax (regex offline + LLM fallback)

Python: `from qleric import parse, query; query(parse(data, "pdf"), INVOICE_FIELDS)`.
