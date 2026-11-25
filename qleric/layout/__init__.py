"""Pluckable layout: sentences, sections, windows. stdlib only."""
from __future__ import annotations

from .sentences import _sentences
from .types import SECTION_DEFAULTS, FieldAnchors
from .windows import candidates

__all__ = ["FieldAnchors", "SECTION_DEFAULTS", "_sentences", "candidates"]
