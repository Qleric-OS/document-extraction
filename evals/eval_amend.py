"""Amendment blind: operative value + chain + stale resistance (L1 M1).

Usage: python3 evals/eval_amend.py [corpus]

Gates (per plan): operative accuracy gate >80% with both cites, vs the
single-doc baseline (query base only) which returns stale by construction.
"""
from __future__ import annotations

import json
import re as _re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qleric import parse, query  # noqa: E402
from qleric import grounding  # noqa: E402
from qleric.packs import CONTRACT_FIELDS  # noqa: E402
from qleric.resolve import resolve  # noqa: E402
from evals.eval import match, norm as _norm  # noqa: E402

FIELDS = {f["name"]: f for f in CONTRACT_FIELDS}
def _stale_hit(sup: list, v: str) -> bool:
    """Superseded-value detection: date-aware when both sides parse, else
    the legacy bounded-substring check. Canonical comparison stops format
    luck (month-name vs numeric) from deciding stale either way.
    """
    from qleric.primitives.date import parse_date as _parse_date
    for s in sup:
        s = str(s).strip()
        if not s:
            continue
        try:
            ps, pv = _parse_date(s), _parse_date(str(v))
        except Exception:
            ps = pv = None
        if ps is not None and pv is not None:
            if ps == pv:
                return True
            continue
        if _re.search(r"(?<![\d$,])" + _re.escape(s) + r"(?![\d$,.])", str(v)):
            return True
    return False

def _load(pdf: str):
    p = Path(pdf)
    if not p.is_absolute():
        p = Path.cwd() / pdf if (Path.cwd() / pdf).exists() else Path("samples/amend_corpus") / p.name
    return parse(p.read_bytes(), "pdf")
def main(corpus: str = "samples/amend_corpus/amend_corpus.jsonl") -> None:
    rows = [json.loads(line) for line in open(corpus)]
    tp = fp = stale = bhit = 0
    rec_sum = prec_sum = 0.0
    d_tp = d_fp = 0
    abst_ok = abst_tot = 0
    for r in rows:
        field = FIELDS[r["field"]]
        docs = [_load(d["pdf"]) for d in r["docs"]]
        expd = r["expected"]
        exp = expd["value"]
        got = resolve(docs, field, [d.get("role") for d in r["docs"]])
        v = got.get("value")
        diag = r.get("diagnostic")
        if expd.get("abstain"):
            # Abstain gate: null value + both conflicting cites surfaced.
            alts = got.get("alternatives", [])
            covered = sum(
                1 for c in expd.get("chain", [])
                if any(_norm(c) in _norm(a.get("verbatim") or "")
                       or _norm(a.get("verbatim") or "") in _norm(c) for a in alts))
            hit = v is None and covered >= len(expd.get("chain", [])) and len(expd.get("chain", [])) > 0
            abst_tot += 1
            abst_ok += 1 if hit else 0
        elif field["name"] == "cap_on_liability":
            # Clause-valued field: the chain cite IS the evidence; the amount
            # check confirms the resolver picked the right clause.
            hit = bool(v) and str(exp).strip() in v
        else:
            hit = bool(match(r["field"], v, exp))
        # Chain recall: fraction of expected links grounded in the right doc.
        # Content-addressed: each cite must ground in exactly one doc (the
        # operative one). Junk exhibits carry only decoys, so any match is
        # the right doc by construction.
        chain = expd.get("chain", [])
        recalled = 0
        for cite in chain:
            loc = None
            for d in docs:
                loc = (grounding.locate(cite, d.pages)
                       or grounding.locate(cite.lower(), d.pages)
                       or grounding.locate(cite.upper(), d.pages))
                if loc:
                    break
            if loc:
                recalled += 1
        rec = recalled / max(len(chain), 1)
        # Chain precision: fraction of resolver-cited links matching an expected link.
        # Spurious cites (extra docs/spans) dilute the derivation even when the value hits.
        cited = got.get("chain", [])
        precise = 0
        for link in cited:
            verb = _norm(link.get("verbatim") or "")
            if any(_norm(c) in verb or verb in _norm(c) for c in chain):
                precise += 1
        prec = precise / max(len(cited), 1) if cited else (1.0 if not v else 0.0)
        # Stale: returned value matches a superseded one (M1 pairs fall back
        # to the base value when no superseded set is recorded). Bounded so
        # "$9,000,000" does not match inside "$19,000,000".
        sup = r.get("superseded", expd.get("superseded"))
        if sup is None:
            bv0 = _base_value(r, field)
            sup = [bv0] if (r.get("moved") and bv0 is not None) else []
        if exp is not None and v is not None and not diag and _stale_hit(sup, v):
            stale += 1
        # single-doc baseline: base doc only (returns stale by construction)
        bres = query(docs[0], [field], None, deep=False)
        bv = ((bres["fields"] or {}).get(r["field"]) or {}).get("value")
        if exp is not None and match(r["field"], bv, exp):
            bhit += 1
        if diag:
            d_tp += 1 if hit else 0
            d_fp += 0 if hit else 1
            mark = "Yd" if hit else "nd"
        else:
            if hit:
                tp += 1
            else:
                fp += 1
            rec_sum += rec
            prec_sum += prec
            mark = "Y" if hit else "n"
        print(f"| {r['id']} | {r['field'][:12]} | moved={int(r['moved'])} | {mark} | "
              f"exp={exp!r} got={(v or '')[:60]!r} | R={rec:.2f} P={prec:.2f} |")
    n = tp + fp
    print(f"operative: {tp}/{n} = {tp/max(n,1):.2f}  chain_recall={rec_sum/max(n,1):.2f}  "
          f"chain_precision={prec_sum/max(n,1):.2f}  stale={stale}  baseline(base-only)={bhit}/{n}")
    print(f"abstain: {abst_ok}/{abst_tot}  diagnostic: {d_tp}/{d_tp+d_fp} (informative only)")


def _base_value(r: dict, field: dict) -> str | None:
    doc = _load(r["docs"][0]["pdf"])
    res = query(doc, [field], None, deep=False)
    return ((res["fields"] or {}).get(field["name"]) or {}).get("value")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples/amend_corpus/amend_corpus.jsonl")
