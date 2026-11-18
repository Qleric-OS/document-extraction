"""Period primitive: renewal/notice/cure durations to canonical form.

Relocated from qleric.packs.contract, unchanged. Truth sets favor digits
("12 months"); the tidy step canonicalizes number-words and unit number.
"""
from __future__ import annotations

import re as _re


_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
              "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
              "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
              "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
              "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
              "fifty": "50", "sixty": "60", "eighty": "80", "ninety": "90"}


_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "eighty": 80, "ninety": 90}

def _tidy_period(v: str | None) -> str | None:
    """Canonicalize a captured renewal region; truths favor digits ("12 months")."""
    if not v:
        return None
    v = v.replace("-", " ")
    v = _re.sub(r"\s+(terms?|periods?)\s*$", "", v, flags=_re.I).strip()
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", v):
        return "perpetual"
    m = _re.search(r"(?i)\b(successive\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|eighty|ninety|\d+)(?:\s*\(\d+\))?\s*(years?|months?|weeks?|days?)\b", v)
    if not m:
        return None
    succ, num, unit = m.group(1), m.group(2), m.group(3)
    pre = _re.search(r"(?i)\b(\w+)\s+successive\b", v)
    cnt = None
    if pre and pre.group(1).lower() not in ("for", "of", "and", "the", "to", "in", "on",
                                             "a", "an", "per", "each", "or", "nor", "successive"):
        cnt = pre.group(1)
    num = _NUM_WORDS.get(num.lower(), num)
    paren = _re.search(r"\((\d+)\)", v)
    if paren:
        num = paren.group(1)
    base = "year" if unit.lower().startswith("year") else ("month" if unit.lower().startswith("month") else ("week" if unit.lower().startswith("week") else "day"))
    unit = base if num == "1" else base + "s"
    parts = ([cnt] if cnt else []) + ([succ.strip()] if succ else []) + [f"{num} {unit}"]
    return " ".join(parts).strip() or None


def clean_renewal(raw: str | None) -> str | None:
    """Extract a renewal period from a capture, or None (initial-term-only sections null out)."""
    if not raw:
        return None
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", raw):
        return "perpetual"
    return _tidy_period(raw)


def clean_notice(raw: str | None) -> str | None:
    """Extract a termination-notice period from a captured sentence.

    Breach/cure/default sentences veto: their notice periods answer a
    different question (cure windows, not termination notice). _tidy_period
    then canonicalizes the first duration ("thirty (30) days" -> "30 days").
    """
    if not raw:
        return None
    if _re.search(r"breach|cure|cured|curing|default\w*|failure\s+to", raw, _re.I):
        return None
    return _tidy_period(raw)
