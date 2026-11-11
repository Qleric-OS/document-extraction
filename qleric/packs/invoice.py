"""Invoice pack: strategy per field. local = offline span search, llm = reasoning.

Anchors generalize across layouts ("Invoice #", "Ref:", "Bill no.") without a
pattern per variant. normalize cleans the matched span (strip $, parse dates).
"""
_MONEY = r"([$€£]?\s*(?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)[.,][0-9]{2}\s*(?:EUR|USD|GBP)?|(?:EUR|USD|GBP)\s*(?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)[.,][0-9]{2})"

_DATE = r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2})"

FIELDS = [
    {"name": "invoice_number", "strategy": "local", "hint": "invoice or reference number",
     "anchors": ["invoice number", "invoice no", "invoice #", "inv", "reference",
                 "ref no", "bill no", "order no"],
     "normalize": r"([A-Za-z0-9\-/]+)\s*$"},
    {"name": "invoice_date", "strategy": "local", "hint": "date of issue",
     "anchors": ["invoice date", "date of issue", "dated", "issued"],
     "normalize": _DATE},
    {"name": "due_date", "strategy": "local", "hint": "payment due date",
     "anchors": ["due date", "payment due", "pay by", "due on", "net terms", "terms"],
     "normalize": _DATE},
    {"name": "total_amount", "strategy": "local", "hint": "grand total",
     "anchors": ["total due", "grand total", "amount due", "total amount", "balance due"],
     "normalize": _MONEY},
    {"name": "tax_amount", "strategy": "local", "hint": "tax or VAT amount",
     "anchors": ["tax", "vat", "gst", "sales tax", "vat included", "tax included"],
     "normalize": _MONEY},
    {"name": "seller", "strategy": "llm", "hint": "selling company name"},
    {"name": "buyer", "strategy": "llm", "hint": "buying company name"},
    {"name": "line_items", "strategy": "table", "hint": "line items from item tables",
     "columns": ["description", "qty", "quantity", "price", "amount", "total"]},
]
