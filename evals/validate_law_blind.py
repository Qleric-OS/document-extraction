"""Blind law validation: 20 unseen CUAD docs, law field only, keyless.

Excludes the 12 tuning docs (rows[:12]) plus individually debugged files.
Method attribution per doc: which mechanism produced the value
(direct/couple/demote-avoided/headings/resolve/fallback/null).
"""
from __future__ import annotations

import csv
import os
import random
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from qleric import parse, query  # noqa: E402
from qleric.documents import Document, Page  # noqa: E402
from qleric.packs import CONTRACT_FIELDS  # noqa: E402
from evals.eval import match  # noqa: E402

CUAD = os.getenv("CUAD_DIR", os.path.expanduser("~/Desktop/CUAD_v1"))
SEEN_PREFIXES = set()  # filled from rows[:12] + debugged files at runtime

LAW = next(f for f in CONTRACT_FIELDS if f["name"] == "governing_law")


def main(n: int = 20, seed: int = 7) -> None:
    rows = list(csv.DictReader(open(os.path.join(CUAD, "master_clauses.csv"))))
    seen_files = {r["Filename"] for r in rows[:12]}
    # individually debugged during development
    txtdir0 = os.path.join(CUAD, "full_contract_txt")
    seen_files |= {f for f in os.listdir(txtdir0)
                   if f.startswith(("Cybergy", "Euromedia", "Fulucai"))}
    pool = [r for r in rows
            if r["Filename"] not in seen_files
            and (r.get("Governing Law-Answer") or "").strip()
            and (r.get("Governing Law-Answer") or "").strip() not in ("[]",)]
    rng = random.Random(seed)
    sample = rng.sample(pool, min(n, len(pool)))
    print(f"pool={len(pool)} sampled={len(sample)} (seed {seed})")
    print()
    print("| doc | expected | got | grounded | method |")
    print("|---|---|---|---|---|")
    hits = total = 0
    methods: dict[str, int] = {}
    for r in sample:
        exp = (r.get("Governing Law-Answer") or "").strip()
        if not exp or exp == "[]" or "[*" in exp:
            continue  # redacted/unanswerable truth
        stem = r["Filename"].rsplit(".", 1)[0]
        txtdir = os.path.join(CUAD, "full_contract_txt")
        cand = next((f for f in os.listdir(txtdir) if f.startswith(stem[:30])), None)
        if cand:
            txt = os.path.join(txtdir, cand)
        else:
            pdfdir = os.path.join(CUAD, "full_contract_pdf")
            cand = next((f for f in os.listdir(pdfdir) if f.startswith(stem[:30])), None)
            if not cand:
                print(f"  SKIP {r['Filename'][:40]} (no text or pdf)")
                continue
            txt = os.path.join(pdfdir, cand)
        if not os.path.exists(txt):
            continue
        with open(txt, "rb") as fh:
            data = fh.read()
        try:
            doc = parse(data, "txt")  # type: ignore[arg-type]
        except ValueError:
            doc = Document(format="TXT", pages=[Page(number=1, text=data.decode("utf-8", "replace"))])
        res = query(doc, [LAW], None)
        got = (res["fields"].get("governing_law") or {})
        val, grounded = got.get("value"), got.get("grounded")
        hit = bool(match("governing_law", val, r["Governing Law-Answer"].strip()))
        total += 1
        hits += hit
        method = ("resolve" if got.get("resolved_reference") else
                  (got.get("source") or "null"))
        methods[method] = methods.get(method, 0) + 1
        mark = "Y" if hit else "n"
        print(f"| {r['Filename'][:38]} | {r['Governing Law-Answer'].strip()[:28]} | "
              f"{str(val)[:28]} | {mark} | {method} |")
    print()
    print(f"LAW BLIND: {hits}/{total} = {hits/max(total,1):.2f}, methods={methods}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    main(n, seed)
