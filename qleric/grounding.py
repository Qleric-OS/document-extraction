"""Text grounding: prove every extracted value exists in the source."""
from __future__ import annotations

import re

_LIGATURES = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}


def normalize_text_for_matching(text: str) -> str:
    """Normalize text to handle PDF extraction quirks (ligatures, hyphenation, whitespace)."""
    if not text:
        return ""
    for lig, replacement in _LIGATURES.items():
        text = text.replace(lig, replacement)
    text = re.sub(r"-\s*\n\s*", "", text)  # de-hyphenate line breaks
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def fuzzy_text_exists(needle: str, haystack: str, threshold: float = 0.85) -> bool:
    """True if needle is in haystack: exact normalized match or word overlap >= threshold."""
    if not needle or not haystack:
        return False
    norm_needle = normalize_text_for_matching(needle)
    norm_haystack = normalize_text_for_matching(haystack)
    if norm_needle in norm_haystack:
        return True
    needle_words = set(norm_needle.split())
    if len(needle_words) >= 3:
        haystack_words = set(norm_haystack.split())
        if len(needle_words & haystack_words) / len(needle_words) >= threshold:
            return True
    return False


def locate(needle: str, pages: list, threshold: float = 0.85) -> dict | None:
    """Find which page a verbatim quote lives on. Returns {page_number, snippet} or None."""
    if not needle:
        return None
    for page in pages:
        text = page.text if hasattr(page, "text") else page.get("text", "")
        number = page.number if hasattr(page, "number") else page.get("number")
        if fuzzy_text_exists(needle, text, threshold):
            return {"page_number": number, "snippet": " ".join(needle.split())}
    return None
