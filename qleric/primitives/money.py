"""Money primitive: amount + currency pattern shared across packs.

Relocated from qleric.packs.invoice (_MONEY), unchanged.
"""
from __future__ import annotations


MONEY = r"([$€£]?\s*(?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)[.,][0-9]{2}\s*(?:EUR|USD|GBP)?|(?:EUR|USD|GBP)\s*(?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)[.,][0-9]{2})"
