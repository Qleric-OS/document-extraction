"""Ingest failures. Subclass ValueError so old callers keep working."""
from __future__ import annotations


class IngestError(ValueError):
    """Base for ingest failures. Subclasses ValueError (old callers unaffected)."""


class EncryptedPDF(IngestError):
    """PDF requires a password."""


class NoTextLayer(IngestError):
    """No extractable text and OCR yielded nothing (or was unavailable)."""
