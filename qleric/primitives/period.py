"""Period primitive: renewal/notice/cure durations to canonical form.

Relocated from qleric.packs.contract, unchanged. Truth sets favor digits
("12 months"); the tidy step canonicalizes number-words and unit number.
"""
from __future__ import annotations

import re as _re


_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
              "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
              "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
              "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
              "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
              "fifty": "50", "sixty": "60", "eighty": "80", "ninety": "90"}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "eighty": 80, "ninety": 90}

# Shared duration-matching vocabulary (term_end + renewal_end must agree).
_NUMS = "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r"|\d+"
_NUM = r"\b((?:" + _NUMS + r"))(?:\s*\(\d+\))?\s*-?\s*(years?|months?|weeks?|days?)\b"
_ORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
         "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
_GAP_VETO = (r"notic|non-renewal|terminat|cure|breach|prior\s+the\s+end|renew|extend|prolong|"
             r"additional|further|successor|paid|payable|payment|invoice|at\s+least")
_SENT_VETO = r"notic|non-renewal|paid|payable|payment|invoice"
_TERMHEAD = (r"(?<!renewal\s)(?<!extended\s)(?<!successor\s)(?:initial\s+term\b|"
             r"term\s+of\s+(?:this|the)\s+agreement\b[^.?!]{0,60}?(?:shall\s+(?:be|have)|\bis\b|means)\b|"
             r"term\s+shall\s+be\b|term\s+is\b|"
             r"remain\s+in\s+full\s+force\s+and\s+effect\b|continue\s+in\s+full\s+force\s+and\s+effect\b)")

def _tidy_period(v: str | None) -> str | None:

    """Canonicalize a captured renewal region; truths favor digits ("12 months")."""
    if not v:
        return None
    v = _re.sub(r"(?i)\bannual(?:ly)?\s+(periods?|terms?)\b", "1 year", v)
    v = _re.sub(r"(?i)\bmonth\s*(?:-\s*)?to\s*(?:-\s*)?month\b", "1 month", v)
    v = _re.sub(r"(?i)\b(twenty|thirty|forty|fifty|sixty|eighty|ninety)\s*[-\s]\s*(one|two|three|four|five|six|seven|eight|nine)\b",
                lambda m: str(_TENS[m.group(1).lower()] + int(_NUM_WORDS[m.group(2).lower()])), v)
    v = _re.sub(r"\s+(terms?|periods?)\s*$", "", v, flags=_re.I).strip()
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", v):
        return "perpetual"
    m = _re.search(r"(?i)\b((successive)\s+(?:\w+\s+){0,3}?)?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|eighty|ninety|\d+)(?:\s*\(\d+\))?\s*-?\s*(years?|months?|weeks?|days?)\b", v)
    if not m:
        return None
    succ, num, unit = m.group(2), m.group(3), m.group(4)
    pre = _re.search(r"(?i)\b(\w+)\s+successive\b", v)
    cnt = None
    if pre and (pre.group(1).lower() in _NUM_WORDS or pre.group(1).isdigit()):
        cnt = _NUM_WORDS.get(pre.group(1).lower(), pre.group(1))
    num = _NUM_WORDS.get(num.lower(), num)
    paren = _re.search(r"\((\d+)\)", v)
    if paren:
        num = paren.group(1)
    base = "year" if unit.lower().startswith("year") else ("month" if unit.lower().startswith("month") else ("week" if unit.lower().startswith("week") else "day"))
    unit = base if num == "1" else base + "s"
    parts = ([cnt] if cnt else []) + ([succ.strip()] if succ else []) + [f"{num} {unit}"]
    return " ".join(parts).strip() or None


def clean_renewal(raw: str | None) -> str | None:
    """Extract a renewal period from a capture, or None (initial-term-only sections null out)."""
    if not raw:
        return None
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", raw):
        return "perpetual"
    if _re.search(r"(?i)unlimited\s+(number\s+of\s+)?(successive\s+)?(terms?|renewals?|periods?)", raw):
        return "perpetual"
    return _tidy_period(raw)


def clean_notice(raw: str | None) -> str | None:
    """Extract a termination-notice period from a captured sentence.

    Breach/cure/default sentences veto: their notice periods answer a
    different question (cure windows, not termination notice). _tidy_period
    then canonicalizes the first duration ("thirty (30) days" -> "30 days").
    """
    if not raw:
        return None
    if _re.search(r"breach|cure|cured|curing|default\w*|failure\s+to", raw, _re.I):
        return None
    return _tidy_period(raw)

def term_end(text: str, start_value: str | None, agree_value: str | None = None) -> tuple[str, str] | None:
    """Compute an end date from a term duration + start value.

    Returns (value, term span) or None. Shapes: "initial term of N units"
    (start defaults to the effective value) and "N unit anniversary of
    [the Effective Date | date hereof]" (start follows the named anchor:
    effective or agreement value). Only initial-term durations; renewals
    do not move the expiration truth. Callers must flag output computed.
    """
    from qleric.primitives import date as _D
    num, gap_veto, sent_veto, termhead = _NUM, _GAP_VETO, _SENT_VETO, _TERMHEAD
    cands: list[tuple[str, str, str]] = []  # (kind, start, span)
    for m in _re.finditer(num + r"\s+anniversary\s+of\s+(.{0,60}?)(\.|;|$)", text, _re.IGNORECASE):
        tail = m.group(3)
        if _re.search(gap_veto, m.group(0), _re.I):
            continue
        if _re.search(r"effective\s+date", tail, _re.I):
            cands.append(("anniv-eff", start_value or "", m.group(0)))
        elif _re.search(r"date\s+hereof|execution|signing", tail, _re.I):
            cands.append(("anniv-agr", agree_value or "", m.group(0)))
    for m in _re.finditer(termhead + r"[^.?!]{0,150}?" + num, text, _re.IGNORECASE):
        if _re.search(gap_veto, m.group(0), _re.I):
            continue
        s = max(text.rfind(".", 0, m.start()), text.rfind(";", 0, m.start()),
                text.rfind("\n", 0, m.start())) + 1
        nx = min([x for x in (text.find(".", m.end()), text.find(";", m.end()),
                              text.find("\n", m.end())) if x >= 0] or [len(text)])
        sent = text[s:nx]
        if _re.search(sent_veto, sent, _re.I):
            continue
        cands.append(("initial-agr", agree_value or "", sent.strip()))
        cands.append(("initial-eff", start_value or "", sent.strip()))
    for kind, start_value, span in cands:
        start = _D.parse_date(start_value)
        if not start:
            continue
        m2 = _re.search(num, span, _re.IGNORECASE)
        if not m2:
            continue
        n = _NUM_WORDS.get(m2.group(1).lower(), m2.group(1))
        y, mo, d = _D.add_period(start[0], start[1], start[2], int(n), m2.group(2))
        return (f"{mo}/{d}/{y}", span.strip())
    return None

def _sent_span(text: str, s: int, e: int) -> str:
    """Expand a match to its enclosing sentence (same bounds as term_end)."""
    a = max(text.rfind(".", 0, s), text.rfind(";", 0, s), text.rfind("\n", 0, s)) + 1
    b = min([x for x in (text.find(".", e), text.find(";", e), text.find("\n", e)) if x >= 0]
            or [len(text)])
    return text[a:b].strip()


def _doc_date(text: str) -> tuple[int, int, int] | None:
    """First dated-header line in a doc, parsed; None when absent/unparseable."""
    from qleric.primitives import date as _D
    m = _re.search(r"(?im)^\s*dated\s+(.+)$", text)
    if not m:
        return None
    try:
        return _D.parse_date(m.group(1).strip().rstrip("."))
    except Exception:
        return None


def find_counts(text: str) -> list[tuple[int, str]]:
    """All ordinal renewal counts in a text, with citing sentences.

    Shared by renewal_end (first match wins) and conflict detection
    (any two distinct counts from undated amends = no computable answer).
    """
    _ords = "|".join(sorted(_ORDS, key=len, reverse=True))
    out = []
    for m in _re.finditer(r"\b((?:" + _ords + r"))\b.{0,40}?\brenew\w*\b", text, _re.IGNORECASE):
        sent = _sent_span(text, m.start(), m.end())
        if _re.search(_SENT_VETO, sent, _re.I):
            continue
        out.append((_ORDS[m.group(1).lower()], sent))
    return out


def renewal_end(texts: list[str], starts: list[str | None],
                roles: list[str | None] | None = None) -> tuple[str, list[dict]] | None:
    """Compute an end date from initial term + renewal count, across documents.

    Shapes: an initial-term duration somewhere, a renewal length, and an
    ordinal renewal count ("in its second renewal term"). The count need not
    live with the length (amendments cite counts; base docs define terms).
    Only base + amendment-role docs participate; exhibits and junk docs are
    skipped. Omitted roles preserve legacy behavior (every doc participates).
    Returns (value, cites) with one cite per derivation link, or None.
    Callers must flag output computed.
    """
    op = [i for i in range(len(texts))
          if roles is None or i == 0 or (roles[i] or "").startswith("amend")]
    from qleric.primitives import date as _D
    # Start: first parseable value, base doc first.
    start = None
    for sv in starts:
        start = _D.parse_date(sv) if sv else None
        if start:
            break
    if not start:
        return None
    # Initial-term duration: first match in doc order.
    init = None
    for di in op:
        text = texts[di]
        for m in _re.finditer(_TERMHEAD + r"[^.?!]{0,150}?" + _NUM, text, _re.IGNORECASE):
            if _re.search(_GAP_VETO, m.group(0), _re.I):
                continue
            sent = _sent_span(text, m.start(), m.end())
            if _re.search(_SENT_VETO, sent, _re.I):
                continue
            m2 = _re.search(_NUM, sent, _re.I)
            if not m2:
                continue
            n0 = _NUM_WORDS.get(m2.group(1).lower(), m2.group(1))
            init = (di, int(n0), m2.group(2), sent)
            break
        if init:
            break
    if not init:
        return None
    # Count: latest-dated operative doc bearing a count governs; undated
    # docs count only when no dated doc does. Stated dates break the ties
    # that abstain otherwise (folder order is arbitrary); ties keep folder
    # order. Single doc with a count behaves exactly as before.
    count = None
    dated_best = None
    undated_first = None
    for di in op:
        text = texts[di]
        found = find_counts(text)
        if not found:
            continue
        k, sent = found[0]
        dd = _doc_date(text)
        if dd is None:
            if undated_first is None:
                undated_first = (di, k, sent)
        elif dated_best is None or dd > dated_best[0]:
            dated_best = (dd, di, k, sent)
    if dated_best is not None:
        _, di, k, sent = dated_best
        count = (di, k, sent)
    elif undated_first is not None:
        count = undated_first
    if not count:
        return None
    # Renewal length: prefer the count's doc, then the initial-term doc.
    _verb = r"(?:renew\w*|extend\w*|extension)"
    _ren_pat = (r"\b" + _verb + r"\b.{0,60}?" + _NUM + r"|"
                + _NUM + r"\s+terms?\b.{0,40}?\b" + _verb + r"\b")
    length = None
    for di in [count[0], init[0]] + [i for i in op if i not in (count[0], init[0])]:
        for m in _re.finditer(_ren_pat, texts[di], _re.IGNORECASE):
            sent = _sent_span(texts[di], m.start(), m.end())
            if _re.search(_SENT_VETO, sent, _re.I):
                continue
            m2 = _re.search(_NUM, sent, _re.I)
            if not m2:
                continue
            n1 = _NUM_WORDS.get(m2.group(1).lower(), m2.group(1))
            length = (di, int(n1), m2.group(2), sent)
            break
        if length:
            break
    if not length:
        return None
    y, mo, d = _D.add_period(start[0], start[1], start[2], init[1], init[2])
    y, mo, d = _D.add_period(y, mo, d, count[1] * length[1], length[2])
    cites = [{"doc": init[0], "verbatim": init[3]},
             {"doc": length[0], "verbatim": length[3]},
             {"doc": count[0], "verbatim": count[2]}]
    return (f"{mo}/{d}/{y}", cites)
