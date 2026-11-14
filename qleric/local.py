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


# All tunables in one place. Pack fields may override threshold via
# "threshold" key; everything else is global.
TUNE = {
    "span_threshold": 55.0,      # min anchor score to claim a span
    "proximity_floor": 30.0,     # anchor score that admits pattern boost
    "proximity_boost": 40.0,     # paragraph-embedded value bonus
    "value_first_floor": 41.0,   # distinctive shape admission floor
    "value_first_bonus": 15.0,   # ranking bonus on top of floor
    "heading_bonus": 25.0,       # numbered section heading in span
    "headings_bonus": 50.0,      # field's own section heading present
    "match_first_score": 101.0,  # self-identifying pattern direct hit
    "stop_threshold": 60.0,      # rival-heading stop line
    "long_line": 160,            # paragraph-embedded split threshold
    "min_window": 15,            # shortest clause window kept
    "anchor_similarity": 30.0,   # match_first anchored preference floor
}

def candidates(text: str) -> list[str]:
    """Candidate spans: lines, 2-line windows, and clause windows for long lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    spans = list(lines)
    spans += [" ".join(lines[i:i + 2]) for i in range(len(lines) - 1)]
    for ln in lines:
        if len(ln) > TUNE["long_line"]:  # paragraph-embedded values: split on clause boundaries
            for part in re.split(r";|\(|\)|, the |, and |(?<!\d)\. ", ln):
                part = part.strip()
                if len(part) > TUNE["min_window"]:
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


def find_span(text: str, anchors: list[str], pattern: str,
              reject: str | None = None) -> str | None:
    """Direct pattern hit for self-identifying values (email/phone).

    Prefers anchored spans (pattern + anchor words); falls back to bare values.
    Generic shapes (dates, money, ids) must go through the global assignment
    in core, not here. reject skips known traps (year ranges vs phone).
    """
    def _ok(s: str) -> bool:
        return not (reject and re.search(reject, s, re.IGNORECASE))
    anchored = [s for s in candidates(text)
                if re.search(pattern, s, re.IGNORECASE)
                and score(s, anchors) > TUNE["anchor_similarity"] and _ok(s)]
    if anchored:
        return max(anchored, key=lambda s: score(s, anchors))
    for s in candidates(text):  # bare value fallback (no label at all)
        if re.search(pattern, s, re.IGNORECASE) and _ok(s):
            return s
    return None

def find_section(text: str, field: dict, stop_anchors: list[str] | None = None,
                 stop_fields: list[dict] | None = None) -> str | None:
    """Section body: heading + contiguous lines until a rival heading,
    plus doc-wide reassembly of member-pattern lines (shuffle-proof).

    Reads everything from the field dict: anchors, threshold, member,
    heading, exclude, qualify, reassemble. Only stop anchors stay external
    (they depend on sibling fields, not this one).
    """
    anchors = field.get("anchors", [])
    threshold = field.get("threshold", TUNE["span_threshold"])
    member = field.get("member")
    heading = field.get("heading")
    exclude = field.get("exclude")
    qualify = field.get("qualify")
    reassemble = field.get("reassemble", True)
    if stop_anchors is None:
        if stop_fields is None:
            # Unreachable from query() (core always passes siblings), kept for
            # direct find_section callers.
            from .packs import RESUME_FIELDS  # legacy default
            stop_fields = RESUME_FIELDS
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    starts: list[tuple[int, str]] = [(i, ln) for i, ln in enumerate(lines)]
    for i, ln in enumerate(lines):  # paragraph-embedded headings: clause windows can start
        if len(ln) > TUNE["long_line"]:
            for part in re.split(r";|\(|\)|, the |, and |(?<!\d)\. ", ln):
                part = part.strip()
                if len(part) > TUNE["min_window"]:
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
            if score(ln, stop_anchors) > TUNE["stop_threshold"] and score(ln, anchors) <= score(ln, stop_anchors):
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
