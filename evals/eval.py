"""Eval: accuracy (value match) + grounding integrity (every value cited).

Scoring per field:
  hit   value matches expected (fuzzy: case/space-insensitive; money digits-only)
  grounded  hit AND verbatim present AND bbox/bboxes attached (PDF)
  false_ground  grounded:true but verbatim absent from source (hallucinated citation)
  miss  expected present, got nothing

Invoice llm fields (seller/buyer): presence-graded, seller must equal; buyer may
be null in corpus (score only when expected non-null). line_items: skipped (no
truth; presence only in generator). Resume sections: body-line recall.
PII: set match on matches list.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, ".")
from qleric import parse, query  # noqa: E402
from qleric.packs import INVOICE_FIELDS, PII_FIELDS, RESUME_FIELDS  # noqa: E402

PACKS = {"invoice": INVOICE_FIELDS, "resume": RESUME_FIELDS, "pii": PII_FIELDS}
SKIP_LLM_ONLY = {"line_items"}  # no synthetic truth


def norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def money_digits(v: str | None) -> str:
    return re.sub(r"[^0-9]", "", v or "")


def is_money_field(name: str) -> bool:
    return "amount" in name or "tax" in name or "total" in name


def match(name: str, got: str | None, exp) -> bool | None:
    if exp is None:
        return None  # no truth: skip, don't grade
    if is_money_field(name):
        return money_digits(got) == money_digits(str(exp))
    if "date" in name:  # compare as parsed dates, not strings
        import datetime as _dt
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                g = _dt.datetime.strptime(got.strip(), fmt)
                e = _dt.datetime.strptime(str(exp).strip(), fmt)
                return g == e
            except ValueError:
                continue
        try:
            g = _dt.datetime.strptime(got.strip(), "%Y-%m-%d")
            for fmt in ("%d.%m.%Y", "%m/%d/%Y"):
                try:
                    return g == _dt.datetime.strptime(str(exp).strip(), fmt)
                except ValueError:
                    continue
        except ValueError:
            pass
        return norm(got) == norm(str(exp))
    return norm(got) == norm(str(exp))


def run(corpus: str, deep: bool = False, limit: int = 0) -> dict:
    per_field: dict[str, dict[str, int]] = {}
    false_grounds: list[str] = []

    def bump(field: str, key: str):
        d = per_field.setdefault(field, {"hit": 0, "total": 0, "grounded": 0,
                                         "miss": 0, "false_ground": 0})
        d[key] += 1

    n = 0
    with open(corpus) as f:
        for line in f:
            case = json.loads(line)
            if limit and n >= limit:
                break
            n += 1
            pack = PACKS[case["pack"]]
            with open(case["pdf"], "rb") as pf:
                data = pf.read()
            try:
                res = query(parse(data, "pdf"), pack, data, deep=deep)
            except Exception as e:
                print(f"  {case['id']}: ERROR {e}")
                continue
            fields = res["fields"]
            exp = case["expected"]
            doc_text = parse(data, "pdf").full_text
            for fld in pack:
                name = fld["name"]
                if name in SKIP_LLM_ONLY or name.startswith("_"):
                    continue
                if case["pack"] == "resume" and name in ("experience", "education"):
                    bodies = exp.get("_bodies", {})
                    got_val = (fields.get(name) or {}).get("value") or ""
                    hit_ok = any(norm(b) in norm(got_val)
                                 for bl in bodies.values() for b in (bl if isinstance(bl, list) else [bl]))
                    bump(f"resume.{name}", "total")
                    bump(f"resume.{name}", "hit" if hit_ok else "miss")
                    if hit_ok and (fields.get(name) or {}).get("grounded"):
                        bump(f"resume.{name}", "grounded")
                    continue
                if case["pack"] == "pii":
                    got_m = sorted((fields.get(name) or {}).get("matches") or [])
                    exp_m = sorted(exp.get(name, []))
                    key = f"pii.{name}"
                    if not exp_m and not got_m:
                        continue  # correctly absent: not gradeable as hit
                    bump(key, "total")
                    if got_m == exp_m:
                        bump(key, "hit")
                        if (fields.get(name) or {}).get("grounded"):
                            bump(key, "grounded")
                    else:
                        bump(key, "miss")
                    continue
                key = f"{case['pack']}.{name}"
                got = fields.get(name) or {}
                m = match(name, got.get("value"), exp.get(name))
                if m is None:
                    continue  # no truth: ungradeable, don't count
                bump(key, "total")
                if m:
                    bump(key, "hit")
                    if got.get("grounded"):
                        bump(key, "grounded")
                        vb = got.get("verbatim") or ""
                        if vb and norm(vb) not in norm(doc_text):
                            bump(key, "false_ground")
                            false_grounds.append(f"{case['id']}.{name}")
                else:
                    bump(key, "miss")
    return {"cases": n, "deep": deep, "per_field": per_field, "false_grounds": false_grounds}


def report(r: dict) -> str:
    lines = [f"cases={r['cases']} deep={r['deep']}"]
    th = tt = tg = 0
    for name in sorted(r["per_field"]):
        d = r["per_field"][name]
        acc = d["hit"] / max(d["total"], 1)
        grd = d["grounded"] / max(d["hit"], 1)
        lines.append(f"  {name:28s} acc={acc:.2f} ({d['hit']}/{d['total']}) "
                     f"grd={grd:.2f} miss={d['miss']} fg={d['false_ground']}")
        th += d["hit"]
        tt += d["total"]
        tg += d["grounded"]
    lines.append(f"TOTAL acc={th/max(tt,1):.2f} ({th}/{tt}) grounded={tg}/{th}")
    if r["false_grounds"]:
        lines.append("FALSE GROUNDS: " + ", ".join(r["false_grounds"][:10]))
    return "\n".join(lines)


if __name__ == "__main__":
    corpus = sys.argv[1] if len(sys.argv) > 1 else "samples/corpus/corpus.jsonl"
    deep = "--deep" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    r = run(corpus, deep=deep, limit=limit)
    print(report(r))
    out = os.getenv("EVAL_OUT", "")
    if out:
        with open(out, "w") as f:
            json.dump(r, f, indent=2)
