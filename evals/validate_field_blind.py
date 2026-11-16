"""Blind field validation on unseen CUAD docs, keyless.

Same protocol as the original law validator, parameterized by field:
sampling (seed, exclusions), txt/PDF assembly, mechanism attribution.

Modes:
  value  - compare extracted value to truth with evals.match (law-style)
  flag   - truth is Yes/No; hit iff (value found) == (truth Yes)

Usage:
  python3 evals/validate_field_blind.py governing_law "Governing Law-Answer" 100 7
  python3 evals/validate_field_blind.py termination_for_convenience "Termination For Convenience-Answer" 100 7 --flag
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


def load_doc(relpath: str) -> Document | None:
    txtdir = os.path.join(CUAD, "full_contract_txt")
    stem = relpath.rsplit(".", 1)[0]
    exact = stem + ".txt"
    if exact in os.listdir(txtdir):
        parts = [exact]
    else:
        parts = sorted(f for f in os.listdir(txtdir) if f.startswith(stem))
    if parts:  # one txt (or several parts): assemble in order, track pages
        pages = []
        for p in parts:
            with open(os.path.join(txtdir, p), "rb") as fh:
                t = fh.read().decode("utf-8", "replace")
            pages.append(Page(number=len(pages) + 1, text=t))
        return Document(format="TXT", pages=pages)
    pdfdir = os.path.join(CUAD, "full_contract_pdf")
    cand = next((f for f in os.listdir(pdfdir) if f.startswith(stem[:30])), None)
    if not cand:
        return None
    with open(os.path.join(pdfdir, cand), "rb") as fh:
        data = fh.read()
    ext = "pdf" if cand.lower().endswith(".pdf") else "txt"
    try:
        return parse(data, ext)  # type: ignore[arg-type]
    except ValueError:
        return Document(format="TXT", pages=[Page(number=1, text=data.decode("utf-8", "replace"))])


def ungradeable(exp: str) -> bool:
    return (not exp or exp == "[]" or "[*" in exp or "WHICH" in exp.upper())


def main(field_name: str, column: str, n: int = 20, seed: int = 7, flag: bool = False) -> None:
    field = next(f for f in CONTRACT_FIELDS if f["name"] == field_name)
    rows = list(csv.DictReader(open(os.path.join(CUAD, "master_clauses.csv"))))
    seen_files = {r["Filename"] for r in rows[:12]}
    # individually debugged during development
    txtdir0 = os.path.join(CUAD, "full_contract_txt")
    seen_files |= {f for f in os.listdir(txtdir0)
                   if f.startswith(("Cybergy", "Euromedia", "Fulucai"))}
    pool = [r for r in rows
            if r["Filename"] not in seen_files
            and (r.get(column) or "").strip()
            and (r.get(column) or "").strip() != "[]"]
    rng = random.Random(seed)
    sample = rng.sample(pool, min(n, len(pool)))
    print(f"pool={len(pool)} sampled={len(sample)} (seed {seed})")
    print()
    print("| doc | expected | got | grounded | method |")
    print("|---|---|---|---|---|")
    hits = total = skipped = 0
    tp = fp = tn = fn = 0
    methods: dict[str, int] = {}
    for r in sample:
        exp = (r.get(column) or "").strip()
        if ungradeable(exp):
            skipped += 1
            continue  # redacted / template-variable truth: ungradeable
        doc = load_doc(r["Filename"])
        if doc is None:
            print(f"  SKIP {r['Filename'][:40]} (no text or pdf)")
            skipped += 1
            continue
        os.environ["QLERIC_DEBUG"] = "1"
        res = query(doc, [field], None, deep=False)  # blind protocol is keyless by design
        got = res["fields"].get(field_name) or {}
        val = got.get("value")
        if flag:
            found = val is not None
            want = exp.lower() == "yes"
            hit = found == want
            tp += found and want
            fp += found and not want
            tn += (not found) and (not want)
            fn += (not found) and want
        else:
            hit = bool(match(field_name, val, exp))
        total += 1
        hits += hit
        mech = ",".join(res.get("meta", {}).get("debug", {}).get("mechanisms", {}).get(field_name, []))
        method = ("resolve:" if got.get("resolved_reference") else "") + (mech or got.get("source", "null"))
        methods[method] = methods.get(method, 0) + 1
        mark = "Y" if hit else "n"
        flat = str(val).replace(chr(10), " ")[:28]
        print(f"| {r['Filename'][:38]} | {exp[:28]} | "
              f"{flat} | {mark} | {method} |")
    print()
    print(f"BLIND {field_name}: {hits}/{total} = {hits/max(total,1):.2f} "
          f"(skipped={skipped}), methods={methods}")
    if flag:
        print(f"confusion: TP={tp} FP={fp} TN={tn} FN={fn}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--flag"]
    _field = args[0] if len(args) > 0 else "governing_law"
    _column = args[1] if len(args) > 1 else "Governing Law-Answer"
    _n = int(args[2]) if len(args) > 2 else 20
    _seed = int(args[3]) if len(args) > 3 else 7
    main(_field, _column, _n, _seed, flag="--flag" in sys.argv[1:])
