"""Validate private docs against hand-checked truth. Nothing leaves the machine."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from evals.eval import match, norm  # noqa: E402
from qleric import parse, query  # noqa: E402
from qleric.packs import INVOICE_FIELDS, PII_FIELDS, RESUME_FIELDS  # noqa: E402

PACKS = {"invoice": INVOICE_FIELDS, "resume": RESUME_FIELDS, "pii": PII_FIELDS}


def _load_truth() -> list[dict]:
    try:
        from evals.real_truth_local import REAL as LOCAL  # private overlay
        return LOCAL
    except ImportError:
        pass
    from evals.real_truth import REAL
    return REAL


def main() -> int:
    REAL = _load_truth()
    if not REAL:
        print("No private truth yet: copy evals/real_truth.py EXAMPLE, add your docs to samples/real/.")
        return 0
    total = hits = 0
    for case in REAL:
        with open(case["pdf"], "rb") as f:
            data = f.read()
        res = query(parse(data, "pdf"), PACKS[case["pack"]], data)
        exp = case["expected"]
        print(f"=== {case['id']} {res['meta']['grounding_rate']} ===")
        for name, want in exp.items():
            if name.startswith("_") or want is None:
                continue
            got = (res["fields"].get(name) or {}).get("value")
            ok = match(name, got, want) if not isinstance(want, dict) else None
            if ok is None:
                continue
            total += 1
            hits += bool(ok)
            print(f"  {name}: {'HIT' if ok else 'MISS'} got={str(got)[:60]!r}")
        for sec, bl in exp.get("_bodies", {}).items():
            got = (res["fields"].get(sec) or {}).get("value") or ""
            lines = bl if isinstance(bl, list) else [bl]
            ok = all(norm(b) in norm(got) for b in lines)
            total += 1
            hits += bool(ok)
            print(f"  {sec} body: {'HIT' if ok else 'MISS'}")
    print(f"TOTAL {hits}/{total}")
    return 0 if hits == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
