"""qleric: grounded document extraction. Keyless core, BYOK intelligence."""
from .core import query
from .documents import parse
from .highlight import annotate

__all__ = ["query", "parse", "annotate"]
