"""Retrieval workbench: show what the LLM would see for a field. Tune blind no more.

Usage: python3 evals/retrieve.py <pdf|txt> <pack> <field> [--budget 12000]
Prints ranked windows with scores + per-field stats. Iterate on `retrieve`
keywords until the clause you want is window #1.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qleric import core  # noqa: E402
from qleric.documents import Document, Page, parse  # noqa: E402
from qleric.packs import CONTRACT_FIELDS, INVOICE_FIELDS, PII_FIELDS, RESUME_FIELDS  # noqa: E402

PACKS = {"invoice": INVOICE_FIELDS, "resume": RESUME_FIELDS,
         "pii": PII_FIELDS, "contract": CONTRACT_FIELDS}


def main(path: str, pack: str, field: str, budget: int = 12000) -> None:
    with open(path, "rb") as f:
        data = f.read()
    ext = path.rsplit(".", 1)[-1]
    try:
        doc = parse(data, ext)  # type: ignore[arg-type]
    except ValueError:
        doc = Document(format="TXT", pages=[Page(number=1, text=data.decode("utf-8", "replace"))])
    fld = next(f for f in PACKS[pack] if f["name"] == field)
    ctx, stats = core._targeted_context(doc, [fld], budget=budget)
    print(f"field={field} keys={fld.get('retrieve') or 'hint-derived'}")
    print(f"stats={stats}")
    print("=" * 60)
    for i, w in enumerate(ctx.split("\n\n---\n\n")[:5]):
        print(f"--- window {i} ({len(w)} chars) ---")
        print(w[:600])
        print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         budget=int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == "--budget" else 12000)
