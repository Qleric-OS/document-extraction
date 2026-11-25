"""Portable ingest: bytes + extension -> grounded Document. stdlib + fitz only."""
from __future__ import annotations

from .errors import EncryptedPDF, IngestError, NoTextLayer
from .provenance import INGEST_VERSION, ImagePlacement, PageImages, Provenance
from .types import Document, Page, Table

__all__ = ["Document", "EncryptedPDF", "INGEST_VERSION", "ImagePlacement",
           "IngestError", "NoTextLayer", "Page", "PageImages", "Provenance", "Table"]
