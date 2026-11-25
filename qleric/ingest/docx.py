"""DOCX intake: heading-split pseudo-pages. Images unparsed by design (zeros)."""
from __future__ import annotations

import io

from .errors import NoTextLayer
from .provenance import PageImages, Provenance
from .scripts import _scripts_of
from .types import Document, Page, Table


def parse_docx(data: bytes) -> Document:
    from docx import Document as DocxDocument  # optional dep

    doc = DocxDocument(io.BytesIO(data))
    pages: list[Page] = []
    current: list[str] = []
    number = 1
    for p in doc.paragraphs:
        style = (p.style.name or "").lower()
        if style.startswith("heading") and current:
            pages.append(Page(number=number, text="\n".join(current)))
            number += 1
            current = []
        if p.text.strip():
            current.append(p.text)
    if current:
        pages.append(Page(number=number, text="\n".join(current)))
    tables = [Table(page_number=n + 1,
                    headers=[c.text for c in t.rows[0].cells] if t.rows else [],
                    rows=[[c.text for c in r.cells] for r in t.rows[1:]])
              for n, t in enumerate(doc.tables)]
    if not pages:
        raise NoTextLayer("No text content found.")
    got = [_scripts_of(p.text, set()) for p in pages]
    scripts = [g[0] for g in got]
    shares = [round(g[1], 3) for g in got]
    prov = Provenance(
        parser="docx", sparse_pages=tuple(),
        reading_order=tuple(["legacy"] * len(pages)),
        images=tuple(PageImages(total=0, placements=()) for _ in pages),
        scripts=tuple(scripts), cjk_share=tuple(shares))
    meta = {"ingest": prov.as_dict()}
    return Document(format="DOCX", pages=pages, tables=tables, meta=meta)
