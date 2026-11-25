"""Layout shared types. stdlib only, zero third-party deps."""
from __future__ import annotations

from dataclasses import dataclass


# Section-discovery defaults (same values as local.TUNE today; owned here so
# the package is dependency-closed — stdlib only, nothing to install).
SECTION_DEFAULTS = {
    "span_threshold": 55.0,  # min anchor score to claim a span
    "stop_threshold": 60.0,  # rival-heading stop line
    "long_line": 160,  # paragraph-embedded split threshold
    "min_window": 15,  # shortest clause window kept
}


@dataclass(frozen=True)
class FieldAnchors:
    """The exact field-dict keys section discovery reads (packs stay raw dicts).

    `threshold=None` means "caller default" (today: TUNE/SECTION_DEFAULTS).
    """

    anchors: tuple = ()
    heading: str | None = None
    exclude: str | None = None
    threshold: float | None = None
    member: str | None = None
    qualify: str | None = None
    qualify_strong: str | None = None
    disqualify: str | None = None
    reassemble: bool = True
