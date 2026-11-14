"""qleric CLI: grounded extraction from the terminal.

    qleric invoice.pdf --pack invoice
    qleric resume.pdf --pack resume --deep --annotate -o out.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from qleric import annotate, parse, query
from qleric.packs import CONTRACT_FIELDS, INVOICE_FIELDS, PII_FIELDS, RESUME_FIELDS

PACKS = {"invoice": INVOICE_FIELDS, "resume": RESUME_FIELDS,
         "pii": PII_FIELDS, "contract": CONTRACT_FIELDS}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qleric", description=__doc__.splitlines()[0])
    ap.add_argument("file", help="PDF or DOCX to extract from")
    ap.add_argument("--pack", default="invoice", choices=sorted(PACKS),
                    help="domain pack (default: invoice)")
    ap.add_argument("--deep", action="store_true",
                    help="force LLM over all unmatched fields (needs key)")
    ap.add_argument("--annotate", action="store_true",
                    help="write highlighted PDF beside the output")
    ap.add_argument("-o", "--output", help="write JSON here (default: stdout)")
    ap.add_argument("--model", help="override MODEL env for this run")
    args = ap.parse_args(argv)

    if args.model:
        os.environ["MODEL"] = args.model
    try:
        with open(args.file, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"qleric: cannot read {args.file}: {e}", file=sys.stderr)
        return 2
    ext = args.file.rsplit(".", 1)[-1].lower()
    try:
        doc = parse(data, ext)
    except ValueError as e:
        print(f"qleric: {e}", file=sys.stderr)
        return 2
    try:
        result = query(doc, PACKS[args.pack], data if ext == "pdf" else None,
                       deep=args.deep)
    except Exception as e:
        print(f"qleric: extraction failed: {e}", file=sys.stderr)
        return 1
    if args.annotate and ext == "pdf":
        hits = []
        for r in result["fields"].values():
            if not (r.get("grounded") and r.get("page_number")):
                continue
            if isinstance(r.get("value"), list):
                for it in r["value"]:
                    hits.append({"page_number": it.get("page_number", r["page_number"]),
                                 "quote": it["verbatim"]})
            elif r.get("verbatim"):
                hits.append({"page_number": r["page_number"], "quote": r["verbatim"]})
        out_pdf = (args.output.rsplit(".", 1)[0] + ".annotated.pdf"
                   if args.output else args.file.rsplit(".", 1)[0] + ".annotated.pdf")
        with open(out_pdf, "wb") as f:
            f.write(annotate(data, hits))
        print(f"annotated: {out_pdf}", file=sys.stderr)
    text = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
