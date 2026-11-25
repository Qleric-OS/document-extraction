"""Candidate span generation: lines, 2-line windows, clause windows."""
from __future__ import annotations

import re

from .types import SECTION_DEFAULTS


def candidates(text: str) -> list[str]:
    """Candidate spans: lines, 2-line windows, and clause windows for long lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    spans = list(lines)
    spans += [" ".join(lines[i:i + 2]) for i in range(len(lines) - 1)]
    for ln in lines:
        if len(ln) > SECTION_DEFAULTS["long_line"]:  # paragraph-embedded values: split on clause boundaries
            for part in re.split(r";|\(|\)|, the |, and |(?<!\d)\. ", ln):
                part = part.strip()
                if len(part) > SECTION_DEFAULTS["min_window"]:
                    spans.append(part)
    return spans
