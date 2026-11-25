"""Sentence splitting. Single source (was duplicated in primitives.obligation)."""
from __future__ import annotations

import re


def _sentences(val: str) -> list[str]:
    """Split a section into sentences: newlines, semicolons, non-numeric periods."""
    parts = re.split(r"\n+|;|(?<!\d)\.\s+", val)
    return [p.strip(" .") for p in parts if len(p.strip(" .")) > 3]
