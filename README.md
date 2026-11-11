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

| pack | offline (free) | llm (needs key) |
|---|---|---|
| `invoice` | number, dates, totals, tax, line_items (tables) | seller, buyer |
| `resume` | email, phone, experience §, education § | name, skills, current_title |
| `pii` | email, phone, ssn, credit_card, iban (all occurrences + `bboxes`) | — |
| `contract` | agreement/effective/expiration dates, governing law | parties, termination, renewal, non-compete, exclusivity, MFN |

Add `-F "deep=true"` to force LLM over all unmatched fields, `-F "annotate=true"` for a base64 highlighted PDF.

Python: `from qleric import parse, query; query(parse(data, "pdf"), INVOICE_FIELDS)`.

## Cost (measured, not marketed)

Every LLM call is metered into `meta.cost` (tokens in/out + USD). Keyless runs cost exactly $0.

| run | calls | tokens in/out | cost |
|---|---|---|---|
| 8 CUAD contracts, gpt-6-luna | 8 | 59,703 / 2,210 | **$0.0103 (~$0.0013/doc)** |
| 90-case synthetic corpus, keyless | 0 | 0 / 0 | **$0** |

The local layer resolves 100% of offline fields before any token is spent — the LLM only sees what regex/fuzzy can't name.
