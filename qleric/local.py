"""Local semantic layer: fuzzy span search, offline. Generalizes across packs.

Strategy: for each field, score candidate spans (lines + sliding windows)
against anchor phrases with rapidfuzz. Best span above threshold wins, then
an optional normalizer cleans the value (strip $, parse dates). Grounding
still gates everything downstream.
"""
from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz
except ImportError:  # fallback: exact-word overlap only
    fuzz = None


def candidates(text: str) -> list[str]:
    """Candidate spans: lines, 2-line windows, and clause windows for long lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    spans = list(lines)
    spans += [" ".join(lines[i:i + 2]) for i in range(len(lines) - 1)]
    for ln in lines:
        if len(ln) > 160:  # paragraph-embedded values: split on clause boundaries
            for part in re.split(r";|\(|\)|, the |, and |\. ", ln):
                part = part.strip()
                if len(part) > 15:
                    spans.append(part)
    return spans


def _label(span: str) -> str:
    """Label part of a span: strip trailing values/ids, keep the words."""
    s = re.sub(r"\s*(?:EUR|USD|GBP)\s*$", "", span, flags=re.IGNORECASE)  # trailing code
    s = re.sub(r"\s*[$€£]?\s*[0-9][0-9,./\-]*\s*$", "", s)  # trailing number/date
    s = re.sub(r"\s*[:#]\s*[A-Za-z0-9\-/]*$", "", s)  # trailing :id (only if label remains)
    return s if re.search(r"[a-zA-Z]", s or "") else span

def score(span: str, anchors: list[str]) -> float:
    return _score(span, anchors)


def _score(span: str, anchors: list[str]) -> float:
    label = _label(span)
    if fuzz is None:
        words = set(label.lower().split())
        return max((len(set(a.lower().split()) & words) / max(len(a.split()), 1)
                    for a in anchors), default=0.0) * 100
    # full-string ratio on the label: substring luck (bill no vs Bill date)
    # loses to true matches (Ref vs ref no). No partial fallback.
    return max((fuzz.ratio(label.lower(), a.lower()) for a in anchors), default=0.0)


def find_span(text: str, anchors: list[str], threshold: float = 55.0,
              pattern: str | None = None, match_first: bool = False) -> str | None:
    """Best candidate span matching any anchor, or None.

    match_first: accept a direct pattern hit even without an anchor. Only for
    self-identifying patterns (email/phone); generic shapes (dates, money, ids)
    match everywhere and must go through anchors.
    """
    if pattern and match_first:
        anchored = [s for s in candidates(text)
                    if re.search(pattern, s, re.IGNORECASE)
                    and _score(s, anchors) > 30.0]
        if anchored:
            return max(anchored, key=lambda s: _score(s, anchors))
        for s in candidates(text):  # bare value fallback (no label at all)
            if re.search(pattern, s, re.IGNORECASE):
                return s
    best, best_score = None, threshold
    for span in candidates(text):
        s = _score(span, anchors)
        if s > best_score:
            best, best_score = span, s
    return best

def find_section(text: str, anchors: list[str], threshold: float = 55.0,
                 stop_anchors: list[str] | None = None,
                 member: str | None = None) -> str | None:
    """Section body: heading + contiguous lines until a rival heading,
    plus doc-wide reassembly of member-pattern lines (shuffle-proof).

    Stops only on lines that look like a *different* section heading, not on
    junk or short lines. member collects scattered body lines (job entries,
    degree lines) wherever shuffle put them.
    """
    from .packs import RESUME_FIELDS  # lazy: avoids import cycle at module load
    if stop_anchors is None:
        stop_anchors = [a for f in RESUME_FIELDS if f.get("section")
                        for a in f.get("anchors", [])]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    best_idx, best_score = None, threshold
    for i, ln in enumerate(lines):
        s = _score(ln, anchors)
        if s > best_score:
            best_idx, best_score = i, s
    if best_idx is None:
        return None
    body = []
    for ln in lines[best_idx + 1:]:
        if _score(ln, stop_anchors) > 60.0 and _score(ln, anchors) <= _score(ln, stop_anchors):
            break  # a different section starts
        body.append(ln)
    if member:  # reassemble scattered members doc-wide, drop non-member junk
        keep = [ln for ln in body if re.search(member, ln, re.IGNORECASE)]
        seen = set(keep)
        for ln in lines:
            if ln not in seen and re.search(member, ln, re.IGNORECASE):
                keep.append(ln)
                seen.add(ln)
        order = {ln: i for i, ln in enumerate(lines)}  # restore document order
        keep.sort(key=lambda ln: order.get(ln, 0))
        body = keep
    return "\n".join([lines[best_idx], *body]) if body else lines[best_idx]

def normalize(pattern: str | None, span: str, strip: list[str] | None = None) -> str | None:
    """Clean a span: capture group if pattern matches, else None (no value found)."""
    if not pattern:
        return span.strip()
    m = re.search(pattern, span, re.IGNORECASE)
    if not m:
        return None
    groups = [g for g in m.groups() if g]
    val = (groups[-1] if groups else m.group(0)).strip()
    if strip:
        for w in strip:
            val = re.sub(rf"\s+{w}\s*$", "", val, flags=re.IGNORECASE).strip()
    return val
