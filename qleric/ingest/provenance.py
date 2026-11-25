"""Typed ingest provenance. The only shared kernel besides the payload.

Nothing downstream may read ``meta["ingest"]`` except through these types.
``as_dict()`` reproduces the historical meta shape exactly (plus ``version``),
so the dict stays wire-compatible while code branches on fields.
"""
from __future__ import annotations

from dataclasses import dataclass

INGEST_VERSION = 1


@dataclass(frozen=True)
class ImagePlacement:
    """One placement of an XObject image. xref shared across entries."""

    xref: int
    bbox: tuple | None
    bboxes: tuple
    width: int
    height: int
    colorspace: str
    smask: int
    icon: bool


@dataclass(frozen=True)
class PageImages:
    """Per-page image inventory. `total` counts pre-cap placements."""

    total: int
    placements: tuple  # tuple[ImagePlacement, ...]


@dataclass(frozen=True)
class Provenance:
    """How each page was read. Built by parse; read via fields, never keys."""

    parser: str = "pymupdf-text"
    reading_order: tuple = ()
    ocr_pages: tuple = ()
    ocr_attempted: tuple = ()
    ocr_rotated: tuple = ()
    ocr_engine: str = "none"
    ocr_ms: int = 0
    sparse_pages: tuple = ()
    images: tuple = ()  # tuple[PageImages, ...]
    scripts: tuple = ()
    cjk_share: tuple = ()
    version: int = INGEST_VERSION

    def as_dict(self) -> dict:
        """Historical meta["ingest"] shape, key order preserved, plus version."""
        return {
            "parser": self.parser,
            "ocr_pages": list(self.ocr_pages),
            "ocr_attempted": list(self.ocr_attempted),
            "ocr_rotated": list(self.ocr_rotated),
            "ocr_engine": self.ocr_engine,
            "ocr_ms": self.ocr_ms,
            "sparse_pages": list(self.sparse_pages),
            "reading_order": list(self.reading_order),
            "images": [{"total": pg.total, "images": [
                {"xref": e.xref, "width": e.width, "height": e.height,
                 "colorspace": e.colorspace, "smask": e.smask, "icon": e.icon,
                 "bboxes": [list(b) for b in e.bboxes],
                 "bbox": list(e.bbox) if e.bbox is not None else None}
                for e in pg.placements]} for pg in self.images],
            "scripts": [list(s) for s in self.scripts],
            "cjk_share": list(self.cjk_share),
            "version": self.version,
        }
