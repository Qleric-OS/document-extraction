"""Date primitive: absolute-date pattern shared across packs.

Relocated from qleric.packs.invoice (_DATE), unchanged.
"""
from __future__ import annotations


DATE = r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2})"

_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
         "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def parse_date(s: str | None) -> tuple[int, int, int] | None:
    """Parse a date value to (year, month, day); None when unparseable.

    Mirrors the eval-side canonicalization (ordinals, Nth-day-of-Month,
    comma spacing). Runtime parsing for computed values (term arithmetic).
    """
    import datetime as _dt
    import re as _re
    if not s:
        return None
    v = _re.sub(r"(\d{1,2})(?:st|nd|rd|th)\s+day\s+of\s+([A-Za-z]+),?\s*(\d{4})",
                r"\2 \1, \3", s.strip(), flags=_re.IGNORECASE)
    v = _re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", v)
    v = _re.sub(r",\s*(\d)", r", \1", v)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y",
                "%m/%d/%y", "%d.%m.%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            g = _dt.datetime.strptime(v.strip(), fmt)
            return (g.year, g.month, g.day)
        except ValueError:
            continue
    m = _re.match(r"(?i)([A-Za-z]+)\.? (\d{1,2}),? (\d{4})$", v.strip())
    if m and (m.group(1).lower() in _MONTHS or m.group(1).lower() in _ABBR):
        mon = _MONTHS.get(m.group(1).lower(), _ABBR.get(m.group(1).lower()))
        try:
            _dt.date(int(m.group(3)), mon, min(int(m.group(2)), 28))
        except ValueError:
            return None
        return (int(m.group(3)), mon, int(m.group(2)))
    return None


def add_period(y: int, m: int, d: int, n: int, unit: str) -> tuple[int, int, int]:
    """Add N years/months/weeks/days to a date, clamping month-end."""
    import calendar
    import datetime as _dt
    unit = unit.lower()
    if unit.startswith("week"):
        g = _dt.date(y, m, min(d, calendar.monthrange(y, m)[1])) + _dt.timedelta(weeks=n)
        return (g.year, g.month, g.day)
    if unit.startswith("day"):
        g = _dt.date(y, m, min(d, calendar.monthrange(y, m)[1])) + _dt.timedelta(days=n)
        return (g.year, g.month, g.day)
    total = (m - 1) + (n * 12 if unit.startswith("year") else n)
    ny, nm = y + total // 12, total % 12 + 1
    return (ny, nm, min(d, calendar.monthrange(ny, nm)[1]))
