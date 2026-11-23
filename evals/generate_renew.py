"""Renewal-driven operative dates (L2). Seeded, reproducible.

M1: base states start + initial term + auto-renewal, but NO end date.
The amendment states only the renewal count. Operative end appears nowhere.
No-op controls: count never stated -> start + initial.

M2: variable renewal lengths (base or amend), stated end dates (agree and
disagree -> stated always wins), in-doc duration decoys (sentence veto),
conflicting undated counts (abstain), revert with dated line (metadata
exclusion). Diagnostic split labeled, excluded from the gate.

Undated amends throughout (dated lines are parked v2 decoys except the
revert pair, which tests their exclusion); short lines (<75 chars) per
the M1 generator lesson.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import fitz

rng = random.Random(20261123)
OUT = Path("samples/renew_corpus")
OUT.mkdir(parents=True, exist_ok=True)

JUNK = ["Thank you for your business!", "*** CONFIDENTIAL ***", "Page 1 of 1",
        "Questions? Call support.", "---", "E&OE"]


def _pdf(lines: list[str], name: str) -> str:
    import textwrap
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for ln in lines:
        for w in textwrap.wrap(ln, 80) or [""]:
            page.insert_text((72, y), w)
            y += 15
    path = str(OUT / name)
    doc.save(path)
    return path


def _noise(lines: list[str]) -> list[str]:
    out = []
    for ln in lines:
        r = rng.random()
        if r < 0.07:
            ln = ln.upper()
        elif r < 0.14:
            ln = ln.lower()
        out.append(ln)
        if rng.random() < 0.2:
            out.append(rng.choice(JUNK))
    return ["  " + ln if rng.random() < 0.2 else ln for ln in out]


def _char_noise(lines: list[str]) -> list[str]:
    subs = str.maketrans({"a": "@", "e": "3", "i": "1", "o": "0", "s": "5"})
    return [ln.translate(subs) if (len(ln) > 20 and rng.random() < 0.5) else ln
            for ln in lines]
NUMW = {"two": 2, "three": 3}
ORDS = {"second": 2, "third": 3}
MONTHS = ["January", "March", "June", "September"]
_ALL_M = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _shift(mon: str, dd: str, yy: int, months: int) -> str:
    """Shift a month-name date forward; dd<=28 so no clamping needed."""
    m = _ALL_M.index(mon) + 1 + months
    return f"{_ALL_M[(m - 1) % 12]} {dd}, {yy + (m - 1) // 12}"


def _pair_real(i: int, variant: str) -> dict:
    """Phrasing-realism blind: real-register renewal language, same arithmetic.

    Gated: committed machinery claims generality across phrasings, so these
    count. Only the notice-veto variant is diagnostic (documents sent_veto
    overreach on the most common real evergreen phrasing; v3 input).
    """
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    ord_w = rng.choice(sorted(ORDS))
    cnt = ORDS[ord_w]
    mm, dd, yy = start.replace(",", "").split()
    yy = int(yy)
    v0 = f"{mm} {dd}, {yy + n}"
    init_std = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    renew_std = "It renews automatically for successive one-year terms."
    count_std = f"The Agreement is in its {ord_w} renewal term."
    recital_std = f"This Agreement is entered into as of {start}."

    tag = None
    if variant == "paren-digit":
        renew = "This Agreement shall automatically renew for successive one (1) year periods."
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
    elif variant == "extended":
        renew = "The term will be automatically extended for additional one-year terms."
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
    elif variant == "twelve-month":
        renew = "It renews for successive twelve-month periods."
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
    elif variant == "caps-count":
        renew = renew_std
        init, recital, L, sup = init_std, recital_std, 12, [v0]
        count = f"The Agreement is in its {ord_w} Renewal Term."
    elif variant == "period-count":
        renew = renew_std
        init, recital, L, sup = init_std, recital_std, 12, [v0]
        count = f"The Agreement has entered its {ord_w} renewal period."
    elif variant == "dated-recital":
        renew, init, count, L, sup = renew_std, init_std, count_std, 12, [v0]
        recital = f"This Agreement is dated as of {start}."
    elif variant == "paren-init":
        renew, count, recital, L, sup = renew_std, count_std, recital_std, 12, [v0]
        init = f"The initial term shall be for {n_w} ({n}) years."
    elif variant == "auto-extend":
        renew = "This Agreement will automatically extend for successive one-year terms."
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
    elif variant == "stated-agree-real":
        end = _shift(mm, dd, yy, 12 * n + cnt * 12)
        stated = f"The Expiration Date is {end}."
        base = ["MASTER SERVICES AGREEMENT", recital_std, init_std, start0,
                renew_std, stated]
        amend = ["AMENDMENT NO. 1", count_std]
        docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
                {"role": "amend",
                 "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
        return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
                "field": "expiration_date", "docs": docs, "moved": True,
                "expected": {"value": end, "chain": [stated]},
                "superseded": [v0]}
    elif variant == "stated-disagree-real":
        stated = f"The Expiration Date is {v0}."
        base = ["MASTER SERVICES AGREEMENT", recital_std, init_std, start0,
                renew_std, stated]
        amend = ["AMENDMENT NO. 1", count_std]
        docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
                {"role": "amend",
                 "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
        return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
                "field": "expiration_date", "docs": docs, "moved": True,
                "expected": {"value": v0, "chain": [stated]},
                "superseded": []}
    elif variant == "noop-real":
        renew = "The term will be automatically extended for additional one-year terms."
        base = ["MASTER SERVICES AGREEMENT", recital_std, init_std, start0, renew]
        amend = ["AMENDMENT NO. 1",
                 "Section 9 (Notices) is amended to update the notice address."]
        docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
                {"role": "amend",
                 "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
        end0 = f"{mm} {dd}, {yy + n}"
        return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
                "field": "expiration_date", "docs": docs, "moved": False,
                "expected": {"value": end0, "chain": [init_std]},
                "superseded": []}
    elif variant == "unless-terminated":
        renew = ("This Agreement will automatically renew for successive one-year terms "
                 "unless terminated in accordance with Section 8.")
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
    else:  # notice-veto: diagnostic, expect miss (sent_veto overreach).
        # Single visual line by construction: the veto must see "notice".
        renew = "It renews for successive one-year terms unless notice is given."
        init, count, recital, L, sup = init_std, count_std, recital_std, 12, [v0]
        tag = "notice-veto"
    base = ["MASTER SERVICES AGREEMENT", "3. Term.", recital, init, start0, renew]
    amend = ["AMENDMENT NO. 1", count]
    docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": True,
            "expected": {"value": _shift(mm, dd, yy, 12 * n + cnt * L),
                         "chain": [init, renew, count]},
            "superseded": sup, **({"diagnostic": tag} if tag else {})}


def _pair_perp(i: int, kind: str) -> dict:
    """Perpetual term + operative renewal machinery (precedent verification).

    A stated perpetual term beats arithmetic even with init+start+count
    present: extraction yields "perpetual", core skips compute on it, and
    the resolve override breaks on the non-start, non-computed hit. The
    chain (not just the value) proves the stated path fired. Gated: the
    precedent claims this shape.
    """
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    ord_w = rng.choice(sorted(ORDS))
    mm, dd, yy = start.replace(",", "").split()
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    renew1 = "It renews automatically for successive one-year terms."
    perp = "The initial term is perpetual."
    countA = f"The Agreement is in its {ord_w} renewal term."
    base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0,
            renew1, perp]
    if kind == "perp-dated":
        amend = ["AMENDMENT NO. 1",
                 "The Agreement is in its fourth renewal term.",
                 "Dated June 1, 2021."]
    else:
        amend = ["AMENDMENT NO. 1", countA]
    docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": True,
            "expected": {"value": "perpetual", "chain": [perp]},
            "superseded": []}


def _pair_v3(i: int, kind: str) -> dict:
    """V3 slice 1 (relevance): a mid-folder exhibit speaks operatively.

    The exhibit asserts a count + length in clean unhedged phrasing, so no
    content signal can exclude it — only standing (role) can. Without roles
    the exhibit's count spuriously trips count-conflict abstain (verified:
    roles=None yields None with alternatives citing the exhibit on all
    four). With roles the exhibit is excluded and the amend governs.
    """
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    ord_w = rng.choice(sorted(ORDS))
    cnt = ORDS[ord_w]
    mm, dd, yy = start.replace(",", "").split()
    yy = int(yy)
    v0 = f"{mm} {dd}, {yy + n}"
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    renew1 = "It renews automatically for successive one-year terms."
    countA = f"The Agreement is in its {ord_w} renewal term."
    exhibit = ["EXHIBIT B - RENEWAL TERMS",
               "The Agreement is in its fourth renewal term.",
               "Each renewal term is two years."]
    amend = ["AMENDMENT NO. 1", countA]
    if kind == "order-hijack":
        # base has the renewal clause; exhibit still wins by doc order today.
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew1]
        exp = {"value": _shift(mm, dd, yy, 12 * n + cnt * 12),
               "chain": [init0, renew1, countA]}
        sup = [v0]
    else:  # gap-hijack: no operative length anywhere; exhibit fills the gap.
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0]
        exp = {"value": v0, "chain": [init0]}
        sup = []
    docs = [{"role": "base",
             "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "exhibit",
             "pdf": _pdf(_noise(exhibit), f"rnw_{i:03d}_exhibit.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": True,
            "expected": exp, "superseded": sup}


def _pair_v3b(i: int, kind: str) -> dict:
    """V3 slice 2 (date headers): a bare "Date:" line is metadata, not a move.

    "Dated ..." spans were already excluded; the header rule covers bare
    "Date: <date>" too, with operative-noun protection ("Expiration Date:").
    """
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    mm, dd, yy = start.replace(",", "").split()
    yy = int(yy)
    v0 = f"{mm} {dd}, {yy + n}"
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0,
            "It renews automatically for successive one-year terms."]
    if kind == "date-header-revert":
        amend = ["AMENDMENT NO. 1",
                 "The parties agree not to renew this Agreement.",
                 "This Agreement ends at the end of the initial term.",
                 "Date: June 15, 2020."]
        moved, exp, sup = True, {"value": v0, "chain": [init0]}, []
    else:  # date-header-noop: header date is the only amend date, no move.
        amend = ["AMENDMENT NO. 1",
                 "Section 9 (Notices) is amended to update the notice address.",
                 "Date: June 15, 2020."]
        moved, exp, sup = False, {"value": v0, "chain": [init0]}, []
    docs = [{"role": "base",
             "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": moved,
            "expected": exp, "superseded": sup}
def _pair_v3c(i: int, kind: str) -> dict:
    """V3 slice 3 (date order): latest-dated count governs, not folder-first.

    Two dated amends assert different counts. First-in-folder was accidental
    (loop+break, never designed); stated dates give the principled answer.
    """
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    mm, dd, yy = start.replace(",", "").split()
    yy = int(yy)
    v0 = f"{mm} {dd}, {yy + n}"
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    renew1 = "It renews automatically for successive one-year terms."
    countB = "The Agreement is in its fourth renewal term."
    amendA = ["AMENDMENT NO. 1",
              "The Agreement is in its second renewal term.",
              "Dated January 12, 2021."]
    amendB = ["AMENDMENT NO. 2", countB, "Dated March 15, 2021."]
    base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew1]
    first, second = (amendA, amendB) if kind == "chrono" else (amendB, amendA)
    docs = [{"role": "base",
             "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(first), f"rnw_{i:03d}_amend1.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(second), f"rnw_{i:03d}_amend2.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": True,
            "expected": {"value": _shift(mm, dd, yy, 12 * n + 4 * 12),
                         "chain": [init0, renew1, countB]},
            "superseded": [v0]}


def _pair_m2(i: int, kind: str) -> dict:
    """L2 M2 shapes. All amends undated; rng stream continues after M1."""
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    ord_w = rng.choice(sorted(ORDS))
    cnt = ORDS[ord_w]
    mm, dd, yy = start.replace(",", "").split()
    yy = int(yy)
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    v0 = f"{mm} {dd}, {yy + n}"
    renew1 = "It renews automatically for successive one-year terms."
    count0 = f"The Agreement is in its {ord_w} renewal term."

    if kind == "variable-length":
        # renewal length varies (2nd pair uses months): arithmetic must follow it.
        len_w, L = rng.choice([("two-year", 24), ("six-month", 6)])
        renew_v = f"It renews automatically for successive {len_w} terms."
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew_v]
        amend = ["AMENDMENT NO. 1", count0]
        exp = {"value": _shift(mm, dd, yy, 12 * n + cnt * L),
               "chain": [init0, renew_v, count0]}
        sup, docs_tag = [v0], None
    elif kind == "duration-in-amend":
        # no renewal clause in base: length arrives with the count.
        len_s, L = rng.choice([("two years", 24), ("six months", 6)])
        lend = f"Each renewal term is {len_s}."
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0]
        amend = ["AMENDMENT NO. 1", count0, lend]
        exp = {"value": _shift(mm, dd, yy, 12 * n + cnt * L),
               "chain": [init0, count0, lend]}
        sup, docs_tag = [v0], None
    elif kind == "stated-agree":
        # base states the end date; arithmetic agrees -> stated must stand.
        # recital pins the agreement date: without it agree-extraction may
        # latch onto the stated end date and poison cross-doc starts.
        end = _shift(mm, dd, yy, 12 * n + cnt * 12)
        stated = f"It expires on {end}."
        recital = f"This Agreement is entered into as of {start}."
        base = ["MASTER SERVICES AGREEMENT", recital, "3. Term.", init0,
                start0, renew1, stated]
        amend = ["AMENDMENT NO. 1", count0]
        exp = {"value": end, "chain": [stated]}
        sup, docs_tag = [v0], None
    elif kind == "stated-disagree":
        # stated end (initial only) contradicts arithmetic -> stated still wins.
        stated = f"It expires on {v0}."
        recital = f"This Agreement is entered into as of {start}."
        base = ["MASTER SERVICES AGREEMENT", recital, "3. Term.", init0,
                start0, renew1, stated]
        amend = ["AMENDMENT NO. 1", count0]
        exp = {"value": v0, "chain": [stated]}
        sup, docs_tag = [], None
    elif kind in ("decoy", "decoy-unvetoed"):
        # in-doc duration decoy before the real clause; veto must save it.
        # (unvetoed variant lacks "written notice": diagnostic, expect miss.)
        tail = " by written notice." if kind == "decoy" else "."
        decoy = f"The parties may renew for an additional ninety days{tail}"
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0,
                decoy, renew1]
        amend = ["AMENDMENT NO. 1", count0]
        exp = {"value": _shift(mm, dd, yy, 12 * n + cnt * 12),
               "chain": [init0, renew1, count0]}
        sup, docs_tag = [v0], (None if kind == "decoy" else "decoy-unvetoed")
    elif kind == "conflict":
        # two undated amends assert different counts -> abstain with cites.
        countA = "The Agreement is in its second renewal term."
        countB = "The Agreement is in its fourth renewal term."
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew1]
        docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
                {"role": "amend",
                 "pdf": _pdf(_noise(["AMENDMENT NO. 1", countA]),
                             f"rnw_{i:03d}_amendA.pdf")},
                {"role": "amend",
                 "pdf": _pdf(_noise(["AMENDMENT NO. 2", countB]),
                             f"rnw_{i:03d}_amendB.pdf")}]
        return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
                "field": "expiration_date", "docs": docs, "moved": True,
                "expected": {"value": None, "abstain": True,
                             "chain": [countA, countB]},
                "superseded": []}
    else:  # revert+dated
        # amend ends renewal; dated line is metadata, must not become the value.
        base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew1]
        amend = ["AMENDMENT NO. 1",
                 "The parties agree not to renew this Agreement.",
                 "This Agreement ends at the end of the initial term.",
                 "Dated June 15, 2020."]
        exp = {"value": v0, "chain": [init0]}
        sup, docs_tag = [], None
    docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")},
            {"role": "amend",
             "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")}]
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew",
            "field": "expiration_date", "docs": docs, "moved": True,
            "expected": exp, "superseded": sup,
            **({"diagnostic": docs_tag} if docs_tag else {})}



def _pair(i: int, moved: bool, tag: str | None) -> dict:
    n_w = rng.choice(sorted(NUMW))
    n = NUMW[n_w]
    start = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, 2020"
    ord_w = rng.choice(sorted(ORDS))
    cnt = ORDS[ord_w]
    mm, dd, yy = start.replace(",", "").split()
    end_y = int(yy) + n + cnt
    end = f"{mm} {dd}, {end_y}"
    init0 = f"The initial term shall be for {n_w} years."
    start0 = f"It commences on {start}."
    renew0 = "It renews automatically for successive one-year terms."
    count0 = f"The Agreement is in its {ord_w} renewal term."
    base = ["MASTER SERVICES AGREEMENT", "3. Term.", init0, start0, renew0]
    if moved:
        amend = ["AMENDMENT NO. 1", count0]
        exp = {"value": end, "chain": [init0, renew0, count0]}
        sup = [f"{mm} {dd}, {int(yy) + n}"]
    else:
        amend = ["AMENDMENT NO. 1",
                 rng.choice(["Section 9 (Notices) is amended to update the notice address.",
                             "The parties confirm the support contacts in Schedule 2 remain unchanged."])]
        end0_y = int(yy) + n
        end0 = f"{mm} {dd}, {end0_y}"
        exp = {"value": end0, "chain": [init0]}
        sup = []
    docs = [{"role": "base", "pdf": _pdf(_noise(base), f"rnw_{i:03d}_base.pdf")}]
    if tag == "junk-exhibit":
        junk = ["EXHIBIT C - STANDARD TERMS",
                "Extended terms are typically two years.",
                "Termination requires ninety (90) days notice."]
        docs.append({"role": "exhibit",
                     "pdf": _pdf(_noise(junk), f"rnw_{i:03d}_exhibit.pdf")})
    if tag == "ocr-noise":
        garbled = [_char_noise([ln])[0] if ln != count0 else ln for ln in amend]
        docs.append({"role": "amend",
                     "pdf": _pdf(garbled, f"rnw_{i:03d}_amend.pdf")})
    else:
        docs.append({"role": "amend",
                     "pdf": _pdf(_noise(amend), f"rnw_{i:03d}_amend.pdf")})
    return {"id": f"rnw_{i:03d}", "pack": "contract_renew", "field": "expiration_date",
            "docs": docs, "moved": moved, "expected": exp, "superseded": sup,
            **({"diagnostic": tag} if tag else {})}


def main() -> None:
    cases = []
    i = 0
    for _ in range(14):  # moved: count stated in the amendment
        cases.append(_pair(i, True, None))
        i += 1
    for _ in range(6):  # no-op: count never stated -> start + initial holds
        cases.append(_pair(i, False, None))
        i += 1
    for k in range(2):  # diagnostic: exhibit with loaded decoy duration/count
        c = _pair(900 + k, True, "junk-exhibit")
        cases.append(c)
    cases.append(_pair(902, True, "ocr-noise"))
    for k, kind in enumerate(["variable-length"] * 2 + ["duration-in-amend"] * 2
                             + ["stated-agree"] * 2 + ["stated-disagree"] * 2
                             + ["decoy"] * 2 + ["conflict"] * 2 + ["revert"]):
        cases.append(_pair_m2(100 + k, kind))  # 13 gated M2 pairs
    cases.append(_pair_m2(910, "decoy-unvetoed"))  # diagnostic: expect miss
    for k, variant in enumerate(["paren-digit", "extended", "twelve-month",
                                "caps-count", "period-count", "dated-recital",
                                "paren-init", "auto-extend",
                                "stated-agree-real", "stated-disagree-real",
                                "noop-real", "unless-terminated"]):
        cases.append(_pair_real(200 + k, variant))  # 12 gated realism pairs
    cases.append(_pair_real(911, "notice-veto"))  # diagnostic: expect miss
    for k, kind in enumerate(["order-hijack"] * 2 + ["gap-hijack"] * 2):
        cases.append(_pair_v3(300 + k, kind))  # v3 slice 1: relevance, gated
    for k, kind in enumerate(["date-header-revert"] * 2 + ["date-header-noop"] * 2):
        cases.append(_pair_v3b(310 + k, kind))  # v3 slice 2: date headers, gated
    for k, kind in enumerate(["chrono"] * 2 + ["reverse"] * 2):
        cases.append(_pair_v3c(320 + k, kind))  # v3 slice 3: date order, gated
    for k, kind in enumerate(["perp-undated", "perp-dated"]):
        cases.append(_pair_perp(330 + k, kind))  # perpetual term, gated
    with open(OUT / "renew_corpus.jsonl", "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"wrote {len(cases)} pairs to {OUT}")


if __name__ == "__main__":
    main()
