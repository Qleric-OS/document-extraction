"""Pluckable layout: sentences, sections, windows. stdlib only."""
from __future__ import annotations

from .sections import find_section
from .sentences import _sentences, split_sentences
from .types import SECTION_DEFAULTS, FieldAnchors
from .windows import candidates

__all__ = ["FieldAnchors", "SECTION_DEFAULTS", "_sentences", "candidates",
           "find_section", "split_sentences"]
