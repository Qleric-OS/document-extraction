"""CUAD validation (private): real contracts + clause truth from your Desktop.

Reads ~/Desktop/CUAD_v1/*. Stripped to the contract pack's local fields
(parties/agreement/effective/expiration/governing-law); LLM clause fields
are spot-checked with --deep and a key.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qleric import parse, query  # noqa: E402
from qleric.packs import CONTRACT_FIELDS  # noqa: E402
from evals.eval import match  # noqa: E402

CUAD = os.getenv("CUAD_DIR", os.path.expanduser("~/Desktop/CUAD_v1"))
if not os.path.isdir(CUAD):
    print(f"CUAD corpus not found at {CUAD}. Set CUAD_DIR to a CUAD_v1 checkout to run this validation.")
    raise SystemExit(2)
LOCAL_MAP = [
    ("agreement_date", "Agreement Date-Answer"),
    ("effective_date", "Effective Date-Answer"),
    ("expiration_date", "Expiration Date-Answer"),
    ("governing_law", "Governing Law-Answer"),
]
CLAUSE_MAP = [  # CUAD answer cols are long clause text: grade grounded-cited, not exact
    ("termination_for_convenience", "Termination For Convenience-Answer"),
    ("renewal_term", "Renewal Term-Answer"),
    ("non_compete", "Non-Compete-Answer"),
    ("exclusivity", "Exclusivity-Answer"),
    ("most_favored_nation", "Most Favored Nation-Answer"),
]


def main(limit: int = 10, deep: bool = False) -> None:
    rows = list(csv.DictReader(open(os.path.join(CUAD, "master_clauses.csv"))))
    stats: dict[str, dict[str, int]] = {}
    for r in rows[:limit]:
        txt = os.path.join(CUAD, "full_contract_txt", r["Filename"].replace(".pdf", ".txt"))
        if not os.path.exists(txt):
            continue
        with open(txt, "rb") as f:
            data = f.read()
        try:
            doc = parse(data, "txt")  # type: ignore[arg-type]
        except ValueError:
            from qleric.documents import Document, Page
            doc = Document(format="TXT", pages=[Page(number=1, text=data.decode("utf-8", "replace"))])
        res = query(doc, CONTRACT_FIELDS, None, deep=deep)
        print(f"=== {r['Filename'][:60]} {res['meta'].get('grounding_rate')} ===")
        for ours, theirs in LOCAL_MAP:
            exp = (r.get(theirs) or "").strip()
            if not exp:
                continue
            got = (res["fields"].get(ours) or {}).get("value")
            d = stats.setdefault(ours, {"hit": 0, "total": 0})
            d["total"] += 1
            ok = match(ours, got, exp)
            if ok:
                d["hit"] += 1
            else:
                print(f"  MISS {ours}: got={str(got)[:60]!r} exp={exp[:60]!r}")
        for ours, theirs in CLAUSE_MAP:
            exp = (r.get(theirs) or "").strip()
            if not exp:
                continue
            got = res["fields"].get(ours) or {}
            d = stats.setdefault("clause." + ours, {"hit": 0, "total": 0})
            d["total"] += 1
            if exp.lower() == "no":  # absent: null correct; denial cite also correct
                v = str(got.get("value") or "")
                if not v or re.search(r"neither|no general right|may not|shall not|not entitled", v, re.I):
                    d["hit"] += 1
                else:
                    print(f"  CLAUSE-FP {ours}: val={v[:50]!r} (truth: absent)")
            elif exp.lower() == "yes":  # present: expect grounded cite
                if got.get("grounded") and got.get("value"):
                    d["hit"] += 1
                else:
                    print(f"  CLAUSE-MISS {ours}: grounded={got.get('grounded')} (truth: present)")
            else:  # free text (renewal): expect grounded cite
                if got.get("grounded") and got.get("value"):
                    d["hit"] += 1
                else:
                    print(f"  CLAUSE-MISS {ours}: grounded={got.get('grounded')} "
                          f"val={str(got.get('value'))[:50]!r} (truth has clause)")
    for k, d in stats.items():
        print(f"{k}: {d['hit']}/{d['total']} = {d['hit']/max(d['total'],1):.2f}")
    try:
        from qleric import costs
        print("cost:", costs.total())
    except Exception:
        pass


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 10,
         deep="--deep" in sys.argv)
