"""Amendment-pair corpus for operative-truth (L1 M1). Seeded, reproducible.

20 pairs: base doc + 1 amendment. The amendment either moves a value
(cap amount, end date) or touches something else (no-op control: operative
value stays the base value). Truth records the operative value plus the
expected chain cites; the stale base value is recorded to score the
cardinal error (returning unamended truth) separately.

Kept out of samples/corpus: separate file, separate eval, separate seed.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import fitz

rng = random.Random(20261122)
OUT = Path("samples/amend_corpus")
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



CAP_NOOP = [
    "2. Amendment. Section 9 (Notices) is amended to update the notice address to 4 Park Lane.",
    "4. The parties agree to extend the support hours in Section 11 to weekends.",
]
SECS = ["7", "7.1", "14"]

DATE_NOOP = [
    "2. Amendment. Section 5 (Fees) is amended to update the rate card in Exhibit B.",
    "5. The parties confirm the support contacts in Schedule 2 remain unchanged.",
]
def _pair(i: int, kind: str, moved: bool) -> dict:
    # Every operative sentence fits one visual line (<75 chars): P5 verdicts
    # are sentence-scoped and _sentences splits on newlines, so a wrapped
    # grant (modal and verb on different lines) never fires.
    if kind == "cap":
        old = f"${rng.randint(1, 9)},000,000"
        new = f"${rng.randint(10, 99)},000,000"
        sec = rng.choice(SECS)
        base_sent = f"In no event shall aggregate liability exceed {old}."
        base = ["MASTER SERVICES AGREEMENT",
                f"7. LIMITATION OF LIABILITY.",
                base_sent, "Dated March 3, 2021"]
        if moved:
            amend_sent = f"Section {sec} now reads: aggregate liability shall not exceed {new}."
            amend = ["AMENDMENT NO. 1 TO MASTER SERVICES AGREEMENT",
                     amend_sent, "Dated June 1, 2022"]
            operative, chain = new, [base_sent, amend_sent]
        else:
            amend = ["AMENDMENT NO. 1 TO MASTER SERVICES AGREEMENT",
                     rng.choice(CAP_NOOP), "Dated June 1, 2022"]
            operative, chain = old, [base_sent]
        field = "cap_on_liability"
    else:
        start = f"{rng.choice(['January', 'March', 'June'])} {rng.randint(1, 28)}, 2020"
        old_y, new_y = rng.choice([("2022", "2024"), ("2023", "2025"), ("2021", "2023")])
        old = f"December 31, {old_y}"
        new = f"December 31, {new_y}"
        base_sent = f"It expires on {old}."
        base = ["MASTER SERVICES AGREEMENT",
                f"3. Term. This Agreement commences on {start}.",
                base_sent, f"Dated {start}"]
        if moved:
            amend_sent = f"The term is extended through {new}."
            amend = ["AMENDMENT NO. 1 TO MASTER SERVICES AGREEMENT",
                     amend_sent, "Dated June 1, 2022"]
            operative, chain = new, [base_sent, amend_sent]
        else:
            # No Dated line: a lone date on a no-op amend is indistinguishable
            # from an operative end date single-doc (v2 resolver work).
            amend = ["AMENDMENT NO. 1 TO MASTER SERVICES AGREEMENT",
                     rng.choice(DATE_NOOP)]
            operative, chain = old, [base_sent]
        field = "expiration_date"
    return {"id": f"amd_{i:03d}", "pack": "contract_amend", "field": field,
            "docs": [{"role": "base", "pdf": _pdf(_noise(base), f"amd_{i:03d}_base.pdf")},
                     {"role": "amend", "pdf": _pdf(_noise(amend), f"amd_{i:03d}_amend.pdf")}],
            "moved": moved,
            "expected": {"value": operative, "chain": chain}}

def _pair_delta(i: int, variant: str) -> dict:
    """Cap in-clause change statements ("increased from X to Y").

    Bare operative sentences (short-line discipline holds); the amend header
    line carries context. The fix is field-level only (member delta branch +
    clean delta-accept): no shared P5 code touched, so the obligation blind
    cannot move.
    """
    old = "$5,000,000"
    base_sent = f"In no event shall aggregate liability exceed {old}."
    base = ["MASTER SERVICES AGREEMENT",
            "7. LIMITATION OF LIABILITY.",
            base_sent, "Dated March 3, 2021"]
    amend_head = "AMENDMENT NO. 1 TO MASTER SERVICES AGREEMENT"
    if variant == "delta-up":
        amend_sent = f"Liability is increased from {old} to $9,000,000."
        exp, moved, tag = {"value": "$9,000,000",
                           "chain": [base_sent, amend_sent]}, True, None
    elif variant == "delta-down":
        amend_sent = f"Liability is decreased from {old} to $1,000,000."
        exp, moved, tag = {"value": "$1,000,000",
                           "chain": [base_sent, amend_sent]}, True, None
    else:  # delta-byonly: delta with no new value stated; base must stand.
        amend_sent = "Liability is increased by $5,000,000."
        exp, moved, tag = {"value": old,
                           "chain": [base_sent]}, False, None
    amend = [amend_head, amend_sent, "Dated June 1, 2022"]
    docs = [{"role": "base", "pdf": _pdf(_noise(base), f"amd_{i:03d}_base.pdf")},
            {"role": "amend", "pdf": _pdf(_noise(amend), f"amd_{i:03d}_amend.pdf")}]
    return {"id": f"amd_{i:03d}", "pack": "contract_amend", "field": "cap_on_liability",
            "docs": docs, "moved": moved, "expected": exp,
            **({"diagnostic": tag} if tag else {})}

def _char_noise(lines: list[str]) -> list[str]:
    """OCR-style char substitutions for surrounding (non-operative) text.

    Diagnostic only: callers keep operative sentences raw and noise the
    surroundings, so grounding fuzz tolerance is what's measured.
    """
    out = []
    for ln in lines:
        if rng.random() < 0.5 and len(ln) > 20:
            out.append(ln.translate(str.maketrans(
                {"a": "@", "e": "3", "i": "1", "o": "0", "s": "5"})))
        else:
            out.append(ln)
    return out


def _op_noise(lines: list[str], rate: float) -> list[str]:
    """Per-character OCR substitutions on operative sentences (graduated probe).

    Same substitution model as _char_noise, applied per eligible character
    at the given rate: 1.0 garbles every eligible char, lower rates probe
    the cliff. Digits and $ survive (amounts stay matchable); the failure,
    if any, comes from letters driving discovery and verdicts.
    """
    subs = str.maketrans({"a": "@", "e": "3", "i": "1", "o": "0", "s": "5"})
    return ["".join(ch.translate(subs) if (ch in "aeios" and rng.random() < rate) else ch
                     for ch in ln) for ln in lines]


def _chain(i: int, kind: str, pattern: str) -> list[dict]:
    """Three-doc folders (M2 gated) plus diagnostic probes.

    Returns [case] (or two cases for partial-move folders). Every operative
    sentence fits one visual line (M1 lesson: P5 splits on newlines).
    Conflict amends are undated: without dates there is no precedence
    signal, and recency would be a guess.
    """
    sec = rng.choice(SECS)
    if kind == "cap":
        vals = [f"${rng.randint(1, 9)},000,000" for _ in range(3)]
        while len(set(vals)) < 3:
            vals = [f"${rng.randint(1, 9)},000,000" for _ in range(3)]
        v0, v1, v2 = vals
        base = ["MASTER SERVICES AGREEMENT",
                "7. LIMITATION OF LIABILITY.",
                f"In no event shall aggregate liability exceed {v0}."]
        base_sent = base[2]
        field = "cap_on_liability"
        move1 = f"Section {sec} now reads: aggregate liability shall not exceed {{}}."
        move_exp_h = "Section 2 of Amendment No. 1 is further amended."
        move_exp_g = "Aggregate liability shall not exceed {}."
    else:
        start = f"{rng.choice(['January', 'March', 'June'])} {rng.randint(1, 28)}, 2020"
        olds = [f"December 31, {y}" for y in rng.sample(["2021", "2022", "2023"], 3)]
        v0, v1, v2 = olds
        base = ["MASTER SERVICES AGREEMENT",
                f"3. Term. This Agreement commences on {start}.",
                f"It expires on {v0}."]
        base_sent = base[2]
        field = "expiration_date"
        move1 = "The term is extended through {}."
        move_exp_h = "Section 3 of Amendment No. 1 is further amended."
        move_exp_g = "The new expiry date is {}."
    idp = f"amd_{i:03d}"

    def _doc(lines, name):
        return {"role": name, "pdf": _pdf(_noise(lines), f"{idp}_{name}.pdf")}

    if pattern == "move-move":
        s1 = move1.format(v1)
        s2h = move_exp_h
        s2 = move_exp_g.format(v2)
        docs = [_doc(base, "base"),
                _doc(["AMENDMENT NO. 1", s1, "Dated June 1, 2022"], "amend1"),
                _doc(["AMENDMENT NO. 2", s2h, s2, "Dated January 15, 2023"], "amend2")]
        exp = {"value": v2, "chain": [base_sent, s1, s2]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0, v1]}]
    if pattern in ("move-noop", "noop-move"):
        s1 = move1.format(v1)
        noop = rng.choice(CAP_NOOP if kind == "cap" else DATE_NOOP)
        if pattern == "move-noop":
            docs = [_doc(base, "base"),
                    _doc(["AMENDMENT NO. 1", s1, "Dated June 1, 2022"], "amend1"),
                    _doc(["AMENDMENT NO. 2", noop], "amend2")]
            exp, sup = {"value": v1, "chain": [base_sent, s1]}, [v0]
        else:
            docs = [_doc(base, "base"),
                    _doc(["AMENDMENT NO. 1", noop], "amend1"),
                    _doc(["AMENDMENT NO. 2", s1, "Dated January 15, 2023"], "amend2")]
            exp, sup = {"value": v1, "chain": [base_sent, s1]}, [v0]
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": sup}]
    if pattern == "conflict":
        sa = move1.format(v1)
        sb = move1.format(v2)
        docs = [_doc(base, "base"),
                _doc(["AMENDMENT NO. 1", sa], "amendA"),
                _doc(["AMENDMENT NO. 2", sb], "amendB")]
        exp = {"value": None, "chain": [sa, sb], "abstain": True}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": []}]
    if pattern == "duplicate":
        s1 = move1.format(v1)
        docs = [_doc(base, "base"),
                _doc(["AMENDMENT NO. 1", s1, "Dated June 1, 2022"], "amend1"),
                _doc(["AMENDMENT NO. 1 (RE-FILED)", s1, "Dated June 3, 2022"], "amend1b")]
        exp = {"value": v1, "chain": [base_sent, s1]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0]}]
    if pattern == "explicit":
        s2h = move_exp_h
        s2 = move_exp_g.format(v2)
        s1 = move1.format(v1)
        docs = [_doc(base, "base"),
                _doc(["AMENDMENT NO. 1", s1, "Dated June 1, 2022"], "amend1"),
                _doc(["AMENDMENT NO. 2", s2h, s2, "Dated January 15, 2023"], "amend2")]
        exp = {"value": v2, "chain": [base_sent, s1, s2]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0, v1]}]
    if pattern == "junk":
        if kind == "cap":
            junk = ["EXHIBIT C - FEE SCHEDULE",
                    f"The vendor's aggregate liability shall not exceed {v1}.",
                    "Dated June 1, 2022"]
        else:
            junk = ["EXHIBIT C - MILESTONES",
                    f"Delivery is expected by {v1}.",
                    "Dated June 1, 2022"]
        s1 = move1.format(v2)
        docs = [_doc(base, "base"),
                _doc(junk, "exhibit"),
                _doc(["AMENDMENT NO. 1", s1, "Dated January 15, 2023"], "amend1")]
        exp = {"value": v2, "chain": [base_sent, s1]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0, v1],
                 "diagnostic": "junk-exhibit"}]
    if pattern == "ocr":
        s1 = move1.format(v1)
        head = _char_noise(_noise(["AMENDMENT NO. 1"]))[0]
        tail = _char_noise(_noise(["Dated June 1, 2022"]))[0]
        docs = [_doc(base, "base"),
                {"role": "amend1",
                 "pdf": _pdf([head, s1, tail], f"{idp}_amend1.pdf")}]
        exp = {"value": v1, "chain": [base_sent, s1]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0],
                 "diagnostic": "ocr-noise"}]
    if pattern in ("ocr-op-light", "ocr-op-heavy"):
        rate = 0.15 if pattern == "ocr-op-light" else 1.0
        s1 = move1.format(v1)
        garbled = _op_noise([s1], rate)[0]
        docs = [_doc(base, "base"),
                {"role": "amend1",
                 "pdf": _pdf(["AMENDMENT NO. 1", garbled, "Dated June 1, 2022"],
                             f"{idp}_amend1.pdf")}]
        exp = {"value": v1, "chain": [base_sent, s1]}
        return [{"id": idp, "pack": "contract_amend", "field": field, "docs": docs,
                 "moved": True, "expected": exp, "superseded": [v0],
                 "diagnostic": "ocr-operative"}]
    raise ValueError(pattern)


def _partial(i: int, move_cap: bool) -> list[dict]:
    """One folder, two fields: cap moves (date stays), or the mirror.

    Two case dicts share the same docs. Amendments carry no Dated line:
    a lone date on a no-op amend is indistinguishable from an operative
    end date single-doc (documented v2 work).
    """
    idp = f"amd_{i:03d}"
    cap0 = f"${rng.randint(1, 9)},000,000"
    cap1 = f"${rng.randint(10, 99)},000,000"
    d0 = f"December 31, {rng.choice(['2021', '2022'])}"
    d1 = f"December 31, {rng.choice(['2024', '2025'])}"
    start = "March 3, 2020"
    cap_base = "In no event shall aggregate liability exceed " + cap0 + "."
    date_base = "It expires on " + d0 + "."

    def _doc(lines, name):
        return {"role": name, "pdf": _pdf(_noise(lines), f"{idp}_{name}.pdf")}

    if move_cap:
        cap_sent = ("Section 7 now reads: aggregate liability "
                    "shall not exceed " + cap1 + ".")
        amend = ["AMENDMENT NO. 1", cap_sent]
        cap_chain, cap_sup, cap_moved, cap_val = [cap_base, cap_sent], [cap0], True, cap1
        date_chain, date_sup, date_moved, date_val = [date_base], [], False, d0
    else:
        date_sent = "The term is extended through " + d1 + "."
        amend = ["AMENDMENT NO. 1", date_sent]
        cap_chain, cap_sup, cap_moved, cap_val = [cap_base], [], False, cap0
        date_chain, date_sup, date_moved, date_val = [date_base, date_sent], [d0], True, d1
    base = ["MASTER SERVICES AGREEMENT",
            "7. LIMITATION OF LIABILITY.", cap_base,
            "3. Term. This Agreement commences on " + start + ".",
            date_base]
    docs = [_doc(base, "base"), _doc(amend, "amend1")]
    cap_case = {"id": idp + "c", "pack": "contract_amend",
                "field": "cap_on_liability", "docs": docs, "moved": cap_moved,
                "expected": {"value": cap_val, "chain": cap_chain},
                "superseded": cap_sup}
    date_case = {"id": idp + "d", "pack": "contract_amend",
                 "field": "expiration_date", "docs": docs, "moved": date_moved,
                 "expected": {"value": date_val, "chain": date_chain},
                 "superseded": date_sup}
    return [cap_case, date_case]

def main(n_each: int = 10) -> None:
    cases = []
    i = 0
    for kind in ("cap", "date"):
        for j in range(n_each):
            moved = j < 7  # 7 moved + 3 no-op controls per kind
            cases.append(_pair(i, kind, moved))
            i += 1
    # M2 gated: three-doc folders. IDs amd_100+.
    i = 100
    sched = ([("cap", "move-move")] * 3 + [("date", "move-move")] * 3
             + [("cap", "move-noop"), ("date", "move-noop")]
             + [("cap", "noop-move"), ("date", "noop-move")]
             + [("cap", "conflict")] * 3 + [("date", "conflict")] * 2
             + [("cap", "duplicate"), ("date", "duplicate")]
             + [("cap", "explicit"), ("date", "explicit")]
             + [("cap", "partial"), ("date", "partial")])
    for kind, pattern in sched:
        if pattern == "partial":
            for c in _partial(i, kind == "cap"):
                cases.append(c)
            i += 1
        else:
            cases.extend(_chain(i, kind, pattern))
            i += 1
    # M2 diagnostic (labeled, excluded from the gate): junk exhibits with
    # loaded decoys, one OCR-degraded amendment. IDs amd_900+.
    i = 900
    for kind, pattern in [("cap", "junk"), ("date", "junk"), ("cap", "ocr")]:
        cases.extend(_chain(i, kind, pattern))
        i += 1
    # Cap in-clause deltas. IDs amd_200+. By-only is the no-overreach control.
    for k, variant in enumerate(["delta-up", "delta-down", "delta-byonly"]):
        cases.append(_pair_delta(200 + k, variant))
    # OCR operative garble (graduated probe, cap only). IDs amd_910+.
    i = 910
    for kind, pattern in [("cap", "ocr-op-light"), ("cap", "ocr-op-heavy"),
                          ("cap", "ocr-op-light"), ("cap", "ocr-op-light")]:
        cases.extend(_chain(i, kind, pattern))
        i += 1
    with open(OUT / "amend_corpus.jsonl", "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"wrote {len(cases)} pairs to {OUT}")


if __name__ == "__main__":
    main()
