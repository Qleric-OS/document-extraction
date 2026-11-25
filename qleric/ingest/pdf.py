"""PDF intake: bytes -> pages with text, tables, provenance. Keyless, offline."""
from __future__ import annotations

import io

from .columns import _reorder_page
from .errors import EncryptedPDF, NoTextLayer
from .images import _page_images
from .ocr import _ocr_page, _tesseract_version
from .provenance import Provenance
from .scripts import _scripts_of, _units
from .types import Document, Page, Table


def _tables_from_pdf_page(page, number: int) -> list[Table]:
    try:
        # Lines-strategy detection needs vector rulings; pages without any
        # drawings can't yield tables. Filters ~3/4 of ingest cost on text docs.
        if not page.get_drawings():
            return []
        finder = page.find_tables()
    except Exception:
        return []
    out: list[Table] = []
    try:
        for t in finder:
            try:
                data = t.extract()
            except Exception:
                continue
            if not data:
                continue
            try:  # cells is flat row-major: reshape into per-row rects
                flat = list(t.cells)
                ncols = len(data[0]) if data and data[0] else 0
                if ncols and len(flat) == len(data) * ncols:
                    flat = [flat[i:i + ncols] for i in range(0, len(flat), ncols)]
                def _r(c):
                    return [c.x0, c.y0, c.x1, c.y1] if hasattr(c, "x0") else list(c)
                rects = [[_r(c) for c in row] for row in flat
                         if isinstance(row, (list, tuple))]
            except Exception:
                rects = []
            out.append(Table(page_number=number, headers=[str(c or "") for c in data[0]],
                             rows=[[str(c or "") for c in r] for r in data[1:]],
                             cells=rects[1:] if rects and len(rects) > len(data[1:]) else rects))
    except Exception:
        pass
    return out


def parse_pdf(data: bytes, ocr_lang: str = "eng") -> Document:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    try:
        if doc.is_encrypted:
            raise EncryptedPDF("PDF is encrypted.")
        pages, tables = [], []
        raw, orders, is_ocr, imagelist = [], [], [], []
        ocr_pages, ocr_attempted, ocr_rotated, ocr_ms = [], [], [], 0.0
        for i, page in enumerate(doc, start=1):
            try:
                legacy = page.get_text("text") or ""
            except Exception:
                legacy = ""
            tables.extend(_tables_from_pdf_page(page, i))
            imagelist.append(_page_images(page))
            if legacy.split():
                text, order = _reorder_page(page, legacy)
                raw.append(text)
                orders.append(order)
                is_ocr.append(False)
                continue
            ocr_attempted.append(i)  # imageless page: OCR or nothing
            otext, status, ms = _ocr_page(page, ocr_lang)
            ocr_ms += ms
            if otext:
                ocr_pages.append(i)
                if getattr(page, "rotation", 0) % 360:
                    ocr_rotated.append(i)
                raw.append(otext)
                orders.append("ocr")
                is_ocr.append(True)
            else:
                raw.append("")
                orders.append(f"ocr-{status}")
                is_ocr.append(False)
        multi = len(raw) > 1
        # Throwaway doc: boilerplate needs Document shape; skip set feeds scripts.
        probe = Document(format="PDF",
                         pages=[Page(number=i, text=t) for i, t in enumerate(raw, start=1)],
                         tables=tables)
        skip = probe.boilerplate_lines
        scripts, shares, raw_shares = [], [], []
        for p in probe.pages:
            s, share = _scripts_of(p.text, skip)
            scripts.append(s)
            raw_shares.append(share)
            shares.append(round(share, 3))
        counts = [_units(t, sh) for t, sh in zip(raw, raw_shares)]
        total_words = sum(counts)
        pages = [Page(number=i, text=t, ocr=is_ocr[i - 1],
                      # sparse only if tiny AND a small fraction (covers/maps, not short docs)
                      sparse=bool(multi and n < 30 and n < total_words * 0.1))
                 for i, (t, n) in enumerate(zip(raw, counts), start=1)]
        if not any(p.text.strip() for p in pages):
            if ocr_attempted and _tesseract_version() is None:
                raise NoTextLayer("No text content found (scanned image? "
                                  "install tesseract for OCR fallback).")
            if ocr_attempted:
                raise NoTextLayer("No text content found (OCR fallback found no text).")
            raise NoTextLayer("No text content found (scanned image? OCR not yet supported).")
        prov = Provenance(
            reading_order=tuple(orders), ocr_pages=tuple(ocr_pages),
            ocr_attempted=tuple(ocr_attempted), ocr_rotated=tuple(ocr_rotated),
            ocr_engine=_tesseract_version() or "none", ocr_ms=round(ocr_ms),
            sparse_pages=tuple(p.number for p in pages if p.sparse),
            images=tuple(imagelist), scripts=tuple(scripts),
            cjk_share=tuple(shares))
        meta = {"ingest": prov.as_dict()}
        return Document(format="PDF", pages=pages, tables=tables, meta=meta)
    finally:
        doc.close()
