"""Date primitive: absolute-date pattern shared across packs.

Relocated from qleric.packs.invoice (_DATE), unchanged.
"""
from __future__ import annotations


DATE = r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2})"
