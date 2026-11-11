"""Document intake: PDF/DOCX bytes -> pages with text. Keyless, offline."""
from __future__ import annotations

import io
from dataclasses import dataclass, field


@dataclass
class Table:
    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    cells: list[list[list[float]]] = field(default_factory=list)  # per-row cell rects


@dataclass
class Page:
    number: int
    text: str
    sparse: bool = False  # cover/toc page: little text, skip for spans


@dataclass
class Document:
    format: str
    pages: list[Page]
    tables: list[Table] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if not p.sparse)

    @property
    def body_text(self) -> str:
        """Body text: non-sparse pages, boilerplate lines removed."""
        skip = _boilerplate(self)
        out = []
        for p in self.pages:
            if p.sparse:
                continue
            out += [ln for ln in p.text.splitlines() if ln.strip() not in skip]
        return "\n".join(out)


def _boilerplate(doc: Document, min_pages: int = 3) -> set[str]:
    """Lines repeated across the doc: headers, footers, filing stamps, watermarks."""
    from collections import Counter
    counts: Counter[str] = Counter()
    for p in doc.pages:
        for ln in p.text.splitlines():
            s = ln.strip()
            if len(s) > 4:
                counts[s] += 1
    repeated = {s for s, n in counts.items() if n >= 3}
    if len(doc.pages) >= min_pages:
        pageseen: dict[str, set[int]] = {}
        for p in doc.pages:
            for ln in p.text.splitlines():
                s = ln.strip()
                if len(s) > 4:
                    pageseen.setdefault(s, set()).add(p.number)
        repeated |= {s for s, pg in pageseen.items() if len(pg) >= max(min_pages, len(doc.pages) // 2)}
    return repeated


def _tables_from_pdf_page(page, number: int) -> list[Table]:
    try:
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


def parse_pdf(data: bytes) -> Document:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    try:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted.")
        pages, tables = [], []
        raw = []
        for i, page in enumerate(doc, start=1):
            try:
                text = page.get_text("text") or ""
            except Exception:
                text = ""
            raw.append(text)
            tables.extend(_tables_from_pdf_page(page, i))
        multi = len(raw) > 1
        for i, text in enumerate(raw, start=1):
            pages.append(Page(number=i, text=text,
                              sparse=multi and len(text.split()) < 30))
        if not any(p.text.strip() for p in pages):
            raise ValueError("No text content found (scanned image? OCR not yet supported).")
        return Document(format="PDF", pages=pages, tables=tables)
    finally:
        doc.close()


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
        raise ValueError("No text content found.")
    return Document(format="DOCX", pages=pages, tables=tables)


def parse(data: bytes, extension: str) -> Document:
    ext = extension.lower().lstrip(".")
    if ext == "pdf":
        return parse_pdf(data)
    if ext == "docx":
        try:
            return parse_docx(data)
        except ImportError:
            raise ValueError("python-docx not installed; pip install python-docx for DOCX support.")
    raise ValueError(f"Unsupported extension: {extension}")
