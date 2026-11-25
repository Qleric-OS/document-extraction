"""Script signal + CJK-aware counting. Pure stdlib, no I/O."""
from __future__ import annotations

import re
from collections import Counter


def _script_of(ch: str) -> str | None:
    """Script bucket for one alphabetic char; None when unclassified noise."""
    if not ch.isalpha():
        return None
    o = ord(ch)
    if o < 0x250:
        return "latin"
    if 0x400 <= o <= 0x52F:
        return "cyrillic"
    if (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x2EBEF
            or 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF
            or 0x3130 <= o <= 0x318F or 0x3100 <= o <= 0x312F):
        return "cjk"
    if 0x600 <= o <= 0x77F:
        return "arabic"
    if 0x900 <= o <= 0x97F:
        return "devanagari"
    return "other"


def _scripts_of(text: str, skip: set) -> tuple[list, float]:
    """Top-2 scripts + CJK share over body lines. Short/empty -> (['unknown'], 0)."""
    counts: Counter = Counter()
    for ln in (text or "").splitlines():
        if ln.strip() in skip:
            continue
        for ch in ln:
            s = _script_of(ch)
            if s:
                counts[s] += 1
    if sum(counts.values()) < 20:
        return ["unknown"], 0.0
    total = sum(counts.values())
    top = [s for s, _ in counts.most_common(2)]
    return top, counts.get("cjk", 0) / total


def _units(text: str, cjk_share: float) -> int:
    """Countable units: chars when CJK-dominant (no spaces), words otherwise."""
    if cjk_share >= 0.5:
        return len(re.sub(r"\s", "", text or ""))
    return len((text or "").split())
