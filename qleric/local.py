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
    """Full-string ratio on the label: substring luck (bill no vs Bill date)
    loses to true matches (Ref vs ref no). No partial fallback."""
    label = _label(span)
    if fuzz is None:
        words = set(label.lower().split())
        return max((len(set(a.lower().split()) & words) / max(len(a.split()), 1)
                    for a in anchors), default=0.0) * 100
    return max((fuzz.ratio(label.lower(), a.lower()) for a in anchors), default=0.0)


def find_span(text: str, anchors: list[str], threshold: float = 55.0,
              pattern: str | None = None, match_first: bool = False,
              reject: str | None = None) -> str | None:
    """Best candidate span matching any anchor, or None.

    match_first: accept a direct pattern hit even without an anchor. Only for
    self-identifying patterns (email/phone); generic shapes (dates, money, ids)
    match everywhere and must go through anchors. reject skips known traps
    (year ranges matching the phone pattern).
    """
    def _ok(s: str) -> bool:
        return not (reject and re.search(reject, s, re.IGNORECASE))
    if pattern and match_first:
        anchored = [s for s in candidates(text)
                    if re.search(pattern, s, re.IGNORECASE)
                    and score(s, anchors) > 30.0 and _ok(s)]
        if anchored:
            return max(anchored, key=lambda s: score(s, anchors))
        for s in candidates(text):  # bare value fallback (no label at all)
            if re.search(pattern, s, re.IGNORECASE) and _ok(s):
                return s
    best, best_score = None, threshold
    for span in candidates(text):
        s = score(span, anchors)
        if s > best_score:
            best, best_score = span, s
    return best

def find_section(text: str, anchors: list[str], threshold: float = 55.0,
                 stop_anchors: list[str] | None = None,
                 member: str | None = None,
                 heading: str | None = None,
                 exclude: str | None = None,
                 stop_fields: list[dict] | None = None,
                 qualify: str | None = None,
                 reassemble: bool = True) -> str | None:
    """Section body: heading + contiguous lines until a rival heading,
    plus doc-wide reassembly of member-pattern lines (shuffle-proof).

    heading: regex a line must match to START a section (numbered/article/
    lettered shapes). Without it, any high anchor score starts.
    exclude: regex disqualifying false friends (e.g. 'Termination Agreement'
    as a document title, not a section).
    stop_fields: pack fields whose anchors form the rival-heading set.
    member collects scattered body lines wherever shuffle put them.
    qualify: regex the assembled value must contain, else None (wrong section).
    """
    if stop_anchors is None:
        if stop_fields is None:
            from .packs import RESUME_FIELDS  # legacy default
            stop_fields = RESUME_FIELDS
        stop_anchors = [a for f in stop_fields if f.get("section")
                        for a in f.get("anchors", [])]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    starts: list[tuple[int, str]] = [(i, ln) for i, ln in enumerate(lines)]
    for i, ln in enumerate(lines):  # paragraph-embedded headings: clause windows can start
        if len(ln) > 160:
            for part in re.split(r";|\(|\)|, the |, and |(?<!\d)\. ", ln):
                part = part.strip()
                if len(part) > 15:
                    starts.append((i, part))  # origin line index preserves doc order
    cands: list[tuple[tuple[int, float], int, str]] = []
    for pos, (origin, ln) in enumerate(starts):
        if exclude and re.search(exclude, ln, re.IGNORECASE):
            continue  # false friend: never a section start
        if heading and not re.search(heading, ln):
            continue  # unheaded span: not a section start (body handled by member)
        s = score(ln, anchors)
        if s <= threshold:
            continue
        density = 0
        if member:
            own = [t for o, t in starts[pos:pos + 4] if o == origin]
            density = len(re.findall(member, " ".join(own), re.IGNORECASE))
        cands.append(((density, s), origin, ln))
    cands.sort(reverse=True)  # densest, highest-scoring first
    for _, origin, span in cands:
        body = []
        best_pos = next((p for p, (o, t) in enumerate(starts) if o == origin and t == span), -1)
        for o2, t2 in starts[best_pos + 1:]:
            if o2 != origin:
                break
            body.append(t2)
        for i, ln in enumerate(lines):
            if i <= origin:
                continue  # heading line itself; body follows (or window covers it)
            if score(ln, stop_anchors) > 60.0 and score(ln, anchors) <= score(ln, stop_anchors):
                break  # a different section starts
            body.append(ln)
        if member:
            # filter contiguous body to member lines (keeps section identity)
            body = [ln for ln in body if re.search(member, ln, re.IGNORECASE)]
            if reassemble:  # shuffled docs: pull scattered members doc-wide
                seen = set(body)
                for ln in lines:
                    if ln not in seen and re.search(member, ln, re.IGNORECASE):
                        body.append(ln)
                        seen.add(ln)
                order = {ln: i for i, ln in enumerate(lines)}
                body.sort(key=lambda ln: order.get(ln, 0))
        val = "\n".join([span, *body]) if body else span
        if qualify and not re.search(qualify, val, re.IGNORECASE):
            continue  # right shape, wrong substance: try next heading
        return val
    return None

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
