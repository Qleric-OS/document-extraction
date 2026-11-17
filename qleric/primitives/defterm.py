"""Defined-term + anaphora resolution: "laws thereof" -> nearest preceding match.

Relocated from qleric.local, unchanged. Generic: works for any field
whose value can be referenced pronominally.
"""
from __future__ import annotations

import re


def resolve_reference(text: str, span: str, field: dict, window: int = 800) -> str | None:
    """Backward anaphora resolution: 'laws thereof' -> nearest preceding match.

    When the winning span contains a pronominal trigger but no extractable
    value, search the preceding `window` chars for the field's own normalize
    patterns. Returns the cleaned value or None. Generic: works for any
    field whose value can be referenced pronominally.
    """
    triggers = field.get("resolve", {}).get("triggers", [])
    if not triggers or not any(re.search(t, span, re.IGNORECASE) for t in triggers):
        return None
    idx = text.find(span[:60])
    if idx < 0:
        return None
    prior = text[max(0, idx - window):idx]
    # antecedent may precede the span OR sit earlier in the same span
    trig = next((t for t in triggers if re.search(t, span, re.IGNORECASE)), "")
    head = span.split(re.search(trig, span, re.IGNORECASE).group(0))[0] if trig else ""
    pats = list(field.get("resolve", {}).get("patterns", []))
    pats += [field.get("normalize") or ""] + list(field.get("normalize_alt") or [])
    best = None
    for pat in pats:
        if not pat:
            continue
        for m in list(re.finditer(pat, prior, re.IGNORECASE)) + list(re.finditer(pat, head, re.IGNORECASE)):
            groups = [g for g in m.groups() if g]
            best = (groups[-1] if groups else m.group(0)).strip()
    if not best:
        return None
    clean = field.get("clean")
    if clean is not None:
        try:
            cleaned = clean(best)
        except Exception:
            return None
        if cleaned is None:
            return None
        # resolved antecedent must look like a proper-noun phrase, not prose:
        # 1-4 words, each capitalized or a small connector (of/and/the/de/la)
        words = cleaned.split()
        connectors = {"of", "and", "the", "de", "la", "di", "du", "der", "van", "von"}
        if not (1 <= len(words) <= 4) or not all(
                w[0].isupper() or w.lower().strip(".,") in connectors for w in words if w):
            return None
        return cleaned
    return best
