"""Entity helpers: typo tolerance + proper-noun shape gate.

Relocated from qleric.packs.contract (clean_jurisdiction), unchanged.
The gate is jurisdiction-agnostic: capitalized words or small connectors.
"""
from __future__ import annotations

PROPER_CONNECTORS = {"of", "and", "the", "de", "la", "du", "der", "van", "von",
                     "di", "da", "le", "les", "el", "al"}


def _ed1(a: str, b: str) -> bool:
    """One insertion, deletion, or substitution apart (typo/OCR tolerance)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long = (a, b) if la < lb else (b, a)
    return any(short == long[:i] + long[i + 1:] for i in range(len(long)))


def is_proper_noun_phrase(val: str, connectors: set[str] | None = None) -> bool:
    """Proper-noun shape: every word capitalized or a small connector.

    Kills "ECOPETROL found in", lone "that"/"any", stray verbs.
    """
    if connectors is None:
        connectors = PROPER_CONNECTORS
    for w in val.split():
        core = w.strip(".,;:()\"'")
        if not core:
            continue
        if core[0].isupper() or "'" in core or core.lower().startswith("mc"):
            continue
        if core.lower() in connectors:
            continue
        return False
    return True
