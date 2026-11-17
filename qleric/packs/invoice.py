"""Invoice pack: strategy per field. local = offline span search, llm = reasoning.

Anchors generalize across layouts ("Invoice #", "Ref:", "Bill no.") without a
pattern per variant. normalize cleans the matched span (strip $, parse dates).
"""
from __future__ import annotations

from qleric.primitives.date import DATE
from qleric.primitives.money import MONEY


FIELDS = [
    {"name": "invoice_number", "strategy": "local", "hint": "invoice or reference number",
     "anchors": ["invoice number", "invoice no", "invoice #", "inv", "reference",
                 "ref no", "bill no", "order no"],
     "normalize": r"([A-Za-z0-9\-/]+)\s*$"},
    {"name": "invoice_date", "strategy": "local", "hint": "date of issue",
     "anchors": ["invoice date", "date of issue", "dated", "issued"],
     "normalize": DATE},
    {"name": "due_date", "strategy": "local", "hint": "payment due date",
     "anchors": ["due date", "payment due", "pay by", "due on", "net terms", "terms"],
     "normalize": DATE},
    {"name": "total_amount", "strategy": "local", "hint": "grand total",
     "anchors": ["total due", "grand total", "amount due", "total amount", "balance due"],
     "normalize": MONEY},
    {"name": "tax_amount", "strategy": "local", "hint": "tax or VAT amount",
     "anchors": ["tax", "vat", "gst", "sales tax", "vat included", "tax included"],
     "normalize": MONEY},
    {"name": "seller", "strategy": "llm", "hint": "selling company name"},
    {"name": "buyer", "strategy": "llm", "hint": "buying company name"},
    {"name": "line_items", "strategy": "table", "hint": "line items from item tables",
     "columns": ["description", "qty", "quantity", "price", "amount", "total"]},
]
