"""MCP server: point your own assistant at local documents. No key in our process.

Tools:
  read_pages(path, pages?)  - page text for grounding context
  find_quote(path, verbatim) - locate a quote -> page + bboxes
  annotate(path, hits)       - burn highlights into a copy, return path
"""
from __future__ import annotations

import json
import sys

from . import highlight
from .documents import parse
from .grounding import locate

TOOLS = [
    {"name": "read_pages",
     "description": "Read page text from a PDF/DOCX. Returns pages with numbers.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "pages": {"type": "array", "items": {"type": "integer"}},
         "extension": {"type": "string", "description": "pdf or docx, guessed from path"}}}},
    {"name": "find_quote",
     "description": "Locate an exact quote: returns page_number + bboxes, or not found.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"}, "verbatim": {"type": "string"},
         "extension": {"type": "string"}}, "required": ["path", "verbatim"]}},
    {"name": "annotate",
     "description": "Highlight quotes in a PDF copy. Hits: [{page_number, quote}]. Returns output path.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "hits": {"type": "array", "items": {"type": "object"}}}, "required": ["path", "hits"]}},
]


def _load(path: str, extension: str | None):
    ext = extension or path.rsplit(".", 1)[-1]
    with open(path, "rb") as f:
        data = f.read()
    return data, parse(data, ext)


def call(name: str, args: dict) -> dict:
    if name == "read_pages":
        data, doc = _load(args["path"], args.get("extension"))
        wanted = set(args.get("pages") or [])
        return {"format": doc.format,
                "pages": [{"number": p.number, "text": p.text} for p in doc.pages
                          if not wanted or p.number in wanted]}
    if name == "find_quote":
        data, doc = _load(args["path"], args.get("extension"))
        hit = locate(args["verbatim"], doc.pages)
        if not hit:
            return {"found": False}
        out = {"found": True, **hit}
        if doc.format == "PDF":
            out["bbox"] = highlight.find_bboxes(data, hit["page_number"], args["verbatim"])
        return out
    if name == "annotate":
        with open(args["path"], "rb") as f:
            data = f.read()
        out = highlight.annotate(data, args["hits"])
        dest = args["path"].rsplit(".", 1)[0] + ".annotated.pdf"
        with open(dest, "wb") as f:
            f.write(out)
        return {"output": dest, "hits": len(args["hits"])}
    return {"error": f"unknown tool: {name}"}


def serve() -> None:
    """Minimal stdio JSON-RPC loop (MCP-compatible initialize/tools/call)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params", {})
        if method == "initialize":
            _reply(mid, {"serverInfo": {"name": "qleric", "version": "0.2.0"}})
        elif method == "tools/list":
            _reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            try:
                _reply(mid, {"content": [{"type": "text",
                                          "text": json.dumps(call(params.get("name", ""),
                                                                  params.get("arguments", {})))}]})
            except Exception as e:
                _reply(mid, None, str(e))
        elif method in ("notifications/initialized",):
            continue
        else:
            _reply(mid, None, f"unknown method: {method}")


def _reply(mid, result, error: str | None = None) -> None:
    msg: dict = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error else "result"] = {"message": error} if error else result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    serve()
