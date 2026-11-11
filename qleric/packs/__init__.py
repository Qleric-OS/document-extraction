"""Domain packs: narrow schemas on top of the grounded core."""
from .contract import FIELDS as CONTRACT_FIELDS
from .invoice import FIELDS as INVOICE_FIELDS
from .pii import FIELDS as PII_FIELDS
from .resume import FIELDS as RESUME_FIELDS

__all__ = ["CONTRACT_FIELDS", "INVOICE_FIELDS", "PII_FIELDS", "RESUME_FIELDS"]
