"""Blind obligation validation: stratified sample across 4 CUAD categories.

Reuses sampling/loading from validate_field_blind (same seeds, exclusions).
Grading is presence-based: a category counts Yes iff >=1 grounded qualifying
obligation is found. Reports per-category TP/FP + acceptance check
(recall >= 50% of sampled Yes AND FP <= 3 per 25).

Usage:
  python3 evals/validate_obligation_blind.py [per_category=25] [seed=7]
"""
from __future__ import annotations

import csv
import os
import random
import re as _re
import sys
import zlib

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from qleric import grounding
from qleric.local import find_section
from qleric.primitives.obligation import CATEGORIES, find_obligations
from evals.validate_field_blind import CUAD, load_doc, ungradeable  # noqa: E402

COLUMNS = {
    "non_compete": "Non-Compete-Answer",
    "exclusivity": "Exclusivity-Answer",
    "no_solicit_customers": "No-Solicit Of Customers-Answer",
    "no_solicit_employees": "No-Solicit Of Employees-Answer",
}

HEADING = r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*"


def _field_for(category: str) -> dict:
    return {
        "name": "obligation_" + category,
        "strategy": "local",
        "section": True,
        "anchors": CATEGORIES[category]["anchors"],
        "heading": HEADING,
        "exclude": None,
        "reassemble": False,
        "member": r"(?i)\b\w+\b",
    }


def main(per_category: int = 25, seed: int = 7) -> None:
    rows = list(csv.DictReader(open(os.path.join(CUAD, "master_clauses.csv"))))
    seen_files = {r["Filename"] for r in rows[:12]}
    txtdir0 = os.path.join(CUAD, "full_contract_txt")
    seen_files |= {f for f in os.listdir(txtdir0)
                   if f.startswith(("Cybergy", "Euromedia", "Fulucai"))}
    totals: dict[str, dict[str, int]] = {}
    for category, column in COLUMNS.items():
        eligible = [r for r in rows if r["Filename"] not in seen_files
                    and (r.get(column) or "").strip()
                    and (r.get(column) or "").strip() not in ("[]",)
                    and not ungradeable((r.get(column) or "").strip())]
        yeses = [r for r in eligible if r.get(column, "").strip().lower() == "yes"]
        nos = [r for r in eligible if r.get(column, "").strip().lower() != "yes"]
        rng = random.Random(seed * 100003 + zlib.crc32(category.encode()))  # deterministic across processes
        n_yes = min(12, len(yeses), per_category)
        n_no = min(len(nos), per_category - n_yes)
        sample = rng.sample(yeses, n_yes) + rng.sample(nos, n_no)
        stat = totals.setdefault(category, {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "skipped": 0, "yes": 0})
        field = _field_for(category)
        for r in sample:
            exp = (r.get(column) or "").strip()
            if ungradeable(exp):
                stat["skipped"] += 1
                continue
            doc = load_doc(r["Filename"])
            if doc is None:
                stat["skipped"] += 1
                continue
            text = "\n".join(p.text for p in doc.pages)
            span = find_section(text, field, stop_fields=[field])
            found = None
            if span:
                for ob in find_obligations(span, category):
                    if grounding.locate(ob["verbatim"], doc.pages):
                        found = ob
                        break
            method = "none"
            if found is not None:
                method = "section"
            if found is None:
                # Fallback for unheaded grants: accept only negated-modal or
                # strong-marker sentences. Weak-only matches stay excluded: the
                # TFC line-grant experiment proved they FP at scale.
                from qleric.primitives import obligation as _O
                for sent in _O._sentences(text):
                    strong_here = bool(_re.search(_O.STRONG, sent, _re.I))
                    neg_here = bool(_re.search(
                        r"\bnot\b|\bnever\b|n't\b|\bneither\b|\bnor\b"
                        r"|prohibit\w*\s+(?:from|against)|\brefrain\w*\s+from"
                        r"|\bbarred\s+from", sent, _re.I))
                    if not (strong_here or neg_here):
                        continue
                    for ob in find_obligations(sent, category):
                        if grounding.locate(ob["verbatim"], doc.pages):
                            found = ob
                            method = "fallback"
                            break
                    if found is not None:
                        break
            want = exp.lower() == "yes"
            if want:
                stat["yes"] += 1
            hit = (found is not None) == want
            if found and want:
                stat["tp"] += 1
            elif found and not want:
                stat["fp"] += 1
            elif not found and not want:
                stat["tn"] += 1
            else:
                stat["fn"] += 1
            mark = "Y" if hit else "n"
            detail = (found["action"] + " / " + (found["party"] or "?")) if found else "-"
            print(f"| {r['Filename'][:36]} | {category[:12]} | {exp[:5]} | {mark} | {method} | {detail[:44]} |")
    print()
    all_tp = all_fp = all_fn = all_tn = all_yes = 0
    for category, s in totals.items():
        n = s["tp"] + s["fp"] + s["tn"] + s["fn"]
        rec = s["tp"] / max(1, s["yes"])
        ok = rec >= 0.5 and s["fp"] <= 3
        print(f"{category}: tp={s['tp']} fp={s['fp']} tn={s['tn']} fn={s['fn']} "
              f"recall={rec:.2f} accept={'PASS' if ok else 'FAIL'} (n={n}, skipped={s['skipped']})")
        all_tp += s["tp"]
        all_fp += s["fp"]
        all_tn += s["tn"]
        all_fn += s["fn"]
        all_yes += s["yes"]
    print(f"TOTAL: {all_tp + all_tn}/{all_tp + all_fp + all_tn + all_fn} "
          f"tp={all_tp} fp={all_fp} tn={all_tn} fn={all_fn}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    main(n, seed)
