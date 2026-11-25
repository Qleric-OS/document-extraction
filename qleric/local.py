"""Local semantic layer: fuzzy span search, offline. Generalizes across packs.

Strategy: for each field, score candidate spans (lines + sliding windows)
against anchor phrases with rapidfuzz. Best span above threshold wins, then
an optional normalizer cleans the value (strip $, parse dates). Grounding
still gates everything downstream.
"""
from __future__ import annotations

import re

from .primitives.defterm import resolve_reference as resolve_reference  # moved here; re-exported for core + external callers
from .layout.sentences import _sentences as _sentences  # single source (moved verbatim)
from .layout.sections import find_section as find_section  # single source (moved verbatim + scorer)
from .layout.windows import candidates  # moved verbatim; stdlib only

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
    "couple_bonus": 30.0,        # verb+jurisdiction tight adjacency
    "demote_penalty": 40.0,     # incorporation/address context present
    "stop_threshold": 60.0,      # rival-heading stop line
    "long_line": 160,            # paragraph-embedded split threshold
    "min_window": 15,            # shortest clause window kept
    "anchor_similarity": 30.0,   # match_first anchored preference floor
}


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


def normalize(pattern: str | None, span: str, strip: list[str] | None = None,
              alternates: list[str] | None = None, clean=None) -> str | None:
    """Clean a span: capture group if pattern matches, else None (no value found).

    alternates: further patterns tried in order (longest-prefix-first grammars).
    clean: post-processor for the captured value, or the whole span when pattern is None (e.g. jurisdiction trimming).
    """
    if not pattern:
        val = span.strip()
        if clean is None:
            return val
        try:
            return clean(val)
        except Exception:
            return None
    m = re.search(pattern, span, re.IGNORECASE)
    if not m and alternates:
        for alt in alternates:
            m = re.search(alt, span, re.IGNORECASE)
            if m:
                break
    if not m:
        return None
    groups = [g for g in m.groups() if g]
    val = (groups[-1] if groups else m.group(0)).strip()
    if clean is not None:
        try:
            return clean(val)
        except Exception:
            return None
    if strip:
        for w in strip:
            val = re.sub(rf"\s+{w}\s*$", "", val, flags=re.IGNORECASE).strip()
    return val
