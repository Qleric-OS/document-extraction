"""Highlight: map a verified verbatim quote back to PDF bboxes + annotated PDF."""
from __future__ import annotations

import io


def find_bboxes(pdf_data: bytes, page_number: int, text: str) -> list[list[float]]:
    """Search the rendered PDF page for rects matching the quote. Lifted from the old engine."""
    import fitz

    if not text or not page_number or page_number < 1:
        return []
    doc = fitz.open(stream=io.BytesIO(pdf_data), filetype="pdf")
    try:
        if page_number > doc.page_count:
            return []
        page = doc[page_number - 1]
        clean = " ".join(text.split())
        rects = page.search_for(clean)
        if not rects and len(clean) > 30:  # fall back to a 30-char window
            rects = page.search_for(clean[:30])
            if not rects:
                mid = len(clean) // 2
                rects = page.search_for(clean[mid:mid + 30])
        return [[r.x0, r.y0, r.x1, r.y1] for r in rects]
    finally:
        doc.close()


def annotate(pdf_data: bytes, hits: list[dict]) -> bytes:
    """Burn highlight annotations into a copy of the PDF. Each hit: {page_number, quote}."""
    import fitz

    doc = fitz.open(stream=io.BytesIO(pdf_data), filetype="pdf")
    try:
        for hit in hits:
            page_number, quote = hit.get("page_number"), hit.get("quote", "")
            if not page_number or not quote or page_number > doc.page_count:
                continue
            page = doc[page_number - 1]
            for inst in page.search_for(" ".join(quote.split())):
                annot = page.add_highlight_annot(inst)
                annot.update()
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()
