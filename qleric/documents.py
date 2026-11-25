"""Document intake: PDF/DOCX bytes -> pages + text. Keyless, offline.

Canonical home is qleric.ingest; this module is a backward-compatible shim.
"""
from __future__ import annotations

from .ingest import (Document, EncryptedPDF, ImagePlacement, IngestError, NoTextLayer,
                     Page, PageImages, Provenance, Table)
from .ingest.api import parse
from .ingest.docx import parse_docx
from .ingest.pdf import parse_pdf

__all__ = ["Document", "EncryptedPDF", "ImagePlacement", "IngestError",
           "NoTextLayer", "Page", "PageImages", "Provenance", "Table",
           "parse", "parse_docx", "parse_pdf"]
