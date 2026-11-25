"""qleric: grounded document extraction. Keyless core, BYOK intelligence."""
from __future__ import annotations

__all__ = ["query", "parse", "annotate"]


def __getattr__(name: str):
    """Lazy re-exports: `import qleric.documents` must not drag core/LM/packs.

    Ingest stays importable on stdlib + fitz alone (portable); heavy tiers
    load only when their names are touched.
    """
    if name == "query":
        from .core import query
        return query
    if name == "parse":
        from .ingest.api import parse
        return parse
    if name == "annotate":
        from .highlight import annotate
        return annotate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
