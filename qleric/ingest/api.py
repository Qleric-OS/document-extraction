"""Public ingest entry point. Pack-agnostic: bytes + extension -> Document."""
from __future__ import annotations

from .docx import parse_docx
from .pdf import parse_pdf
from .types import Document


def parse(data: bytes, extension: str, ocr_lang: str = "eng") -> Document:
    ext = extension.lower().lstrip(".")
    if ext == "pdf":
        return parse_pdf(data, ocr_lang)
    if ext == "docx":
        try:
            return parse_docx(data)
        except ImportError:
            raise ValueError("python-docx not installed; pip install python-docx for DOCX support.")
    raise ValueError(f"Unsupported extension: {extension}")
