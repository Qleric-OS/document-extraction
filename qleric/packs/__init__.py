"""Domain packs: narrow schemas on top of the grounded core."""
from .invoice import FIELDS as INVOICE_FIELDS
from .pii import FIELDS as PII_FIELDS
from .resume import FIELDS as RESUME_FIELDS

__all__ = ["INVOICE_FIELDS", "PII_FIELDS", "RESUME_FIELDS"]
