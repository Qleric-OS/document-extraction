"""Ingest shared types. Zero logic, zero third-party deps."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Table:
    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    cells: list[list[list[float]]] = field(default_factory=list)  # per-row cell rects


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    sparse: bool = False  # cover/toc page: little text, skip for spans
    ocr: bool = False  # true when text comes from OCR fallback


@dataclass(frozen=True)
class Document:
    format: str
    pages: list[Page]
    tables: list[Table] = field(default_factory=list)
    meta: dict = field(default_factory=dict)  # additive ingest provenance

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if not p.sparse)

    @property
    def boilerplate_lines(self) -> set[str]:
        """Lines repeated boilerplate-style (headers/footers/stamps), excluded from body_text."""
        # Direct __dict__ write: frozen __setattr__ is bypassed on purpose (lazy cache).
        cached = self.__dict__.get("_boilerplate_cache")
        if cached is None:
            cached = _boilerplate(self)
            self.__dict__["_boilerplate_cache"] = cached
        return cached

    @property
    def body_text(self) -> str:
        """Body text: non-sparse pages, boilerplate lines removed."""
        skip = self.boilerplate_lines
        out = []
        for p in self.pages:
            if p.sparse:
                continue
            out += [ln for ln in p.text.splitlines() if ln.strip() not in skip]
        return "\n".join(out)


def _boilerplate(doc: Document, min_pages: int = 3) -> set[str]:
    """Lines repeated across the doc: headers, footers, filing stamps, watermarks."""
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
