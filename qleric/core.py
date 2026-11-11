"""Core query: fields -> values, every value grounded to verbatim + bbox.

Each field declares strategy: local (offline span search) or llm (reasoning).
Regex survives only as span normalizer, never as extraction strategy.
"""
from __future__ import annotations

from . import grounding, highlight, local
from .documents import Document
from .lm import LMError, chat

SYSTEM = ("You are a precise document reader. Extract the requested fields. "
          "For each field return value, verbatim (exact substring from the text), "
          "and page_number (1-based). If not found, value is null.")


def _table_items(doc: Document, f: dict) -> list[dict]:
    """Row-grounded line items: header match -> rows as items with cell bboxes."""
    cols = [c.lower() for c in f.get("columns", [])]
    items: list[dict] = []
    for t in doc.tables:
        heads = [h.lower() for h in t.headers]
        if not heads or sum(any(c in h for h in heads) for c in cols) < 2:
            continue  # not an item table: need 2+ column hits
        idx = {c: next((i for i, h in enumerate(heads) if c in h), None) for c in cols}
        for ri, row in enumerate(t.rows):
            cells = t.cells[ri] if ri < len(t.cells) else []
            item = {}
            for c in cols:
                i = idx[c]
                if i is not None and i < len(row):
                    item[c] = row[i].strip()
            if not any(item.values()):
                continue
            verbatim = " ".join(v for v in item.values() if v)
            boxes = [cells[i] for c in cols if (i := idx[c]) is not None and i < len(cells)]
            items.append({**item, "verbatim": verbatim, "bboxes": boxes,
                          "page_number": t.page_number})
    return items


def _schema_hint(fields: list[dict]) -> str:
    names = ", ".join(f["name"] for f in fields)
    return ('{"<field>": {"value": string|null, "verbatim": string|null, '
            f'"page_number": int|null}}  fields: {names}')


def query(doc: Document, fields: list[dict], pdf_data: bytes | None = None,
          deep: bool = False) -> dict:
    """Run extraction. local/pii spans offline, LLM only for llm fields (or deep=True)."""
    import re as _re
    results: dict[str, dict] = {}
    pending: list[dict] = []
    for f in fields:  # offline pass: fuzzy spans + PII sweeps, no key needed
        strategy = f.get("strategy", "llm")
        if strategy == "pii" and f.get("pattern"):
            from .packs.pii import EXCLUDE
            claimed = [m for other in EXCLUDE.get(f["name"], set())
                       for m in (results.get(other, {}).get("matches") or [])]
            matches = []
            for p in doc.pages:
                for m in _re.finditer(f["pattern"], p.text):
                    cand = " ".join(m.group(0).split())
                    if cand in claimed or any(cand in c for c in claimed):
                        continue
                    matches.append(cand)
            if matches:
                first = grounding.locate(matches[0], doc.pages) or {}
                results[f["name"]] = {"value": f"{len(matches)} found",
                                      "matches": matches,
                                      "verbatim": matches[0], **first,
                                      "grounded": True, "source": "pii"}
            continue
        if strategy == "local" and f.get("section"):
            span = local.find_section(doc.full_text, f.get("anchors", []),
                                      member=f.get("member"))
            if span:
                value = local.normalize(f.get("normalize"), span)
                hit = grounding.locate(span.splitlines()[0], doc.pages) or {}
                results[f["name"]] = {"value": value, "verbatim": span.strip(),
                                      **hit, "grounded": True, "source": "local"}
            continue
        if strategy == "table":
            items = _table_items(doc, f)
            if items:
                first = grounding.locate(items[0]["verbatim"], doc.pages) or {}
                results[f["name"]] = {"value": items, "verbatim": items[0]["verbatim"],
                                      **first, "grounded": True, "source": "table",
                                      "bboxes": [b for it in items for b in it["bboxes"]]}
            continue
        if strategy == "local":
            pending.append(f)

    if pending:  # global best-assignment: highest score claims each span first
        scored: list[tuple[float, str, str]] = []  # (score, field, span)
        for f in pending:
            if f.get("match_first") and f.get("normalize"):
                best = local.find_span(doc.full_text, f.get("anchors", []),
                                       pattern=f.get("normalize"), match_first=True)
                if best:
                    scored.append((101.0, f["name"], best))
                continue
            for span in local.candidates(doc.full_text):
                s = local.score(span, f.get("anchors", []))
                if s > 55.0:
                    scored.append((s, f["name"], span))
        scored.sort(reverse=True)
        taken: set[str] = set()
        for _, name, span in scored:
            if name in results or span in taken:
                continue
            f = next(x for x in pending if x["name"] == name)
            value = local.normalize(f.get("normalize"), span)
            hit = grounding.locate(span.splitlines()[0], doc.pages) or {}
            results[name] = {"value": value, "verbatim": span.strip(),
                             **hit, "grounded": True, "source": "local"}
            taken.add(span)
    llm_fields = [f for f in fields
                  if f["name"] not in results
                  and (deep or f.get("strategy", "llm") == "llm")]
    if llm_fields:  # LLM pass: single call, verify locally
        user = "FIELDS:\n" + "\n".join(f"- {f['name']}: {f.get('hint', '')}" for f in llm_fields)
        user += "\n\nDOCUMENT:\n" + "\n\n".join(
            f"[Page {p.number}]\n{p.text}" for p in doc.pages)
        try:
            raw = chat(SYSTEM, user[:100_000], _schema_hint(llm_fields))
        except LMError as e:
            for f in llm_fields:  # keyless: report honestly instead of dropping
                results.setdefault(f["name"], {"value": None, "grounded": False,
                                               "source": f.get("strategy", "llm"),
                                               "note": str(e)})
            return finalize(doc, results, pdf_data)
        for f in llm_fields:
            item = raw.get(f["name"], {}) if isinstance(raw, dict) else {}
            value, verbatim = item.get("value"), item.get("verbatim")
            hit = grounding.locate(verbatim, doc.pages) if verbatim else None
            if value and hit:
                results[f["name"]] = {"value": value, "verbatim": verbatim,
                                      **hit, "grounded": True, "source": "llm"}
            else:
                results[f["name"]] = {"value": value, "verbatim": verbatim,
                                      "grounded": False, "source": "llm",
                                      "page_number": item.get("page_number")}
    else:  # keyless local-only: report misses honestly
        for f in fields:
            results.setdefault(f["name"], {"value": None, "grounded": False,
                                           "source": f.get("strategy", "llm"),
                                           "note": "no local match; needs LLM (deep=true or key)"})
    return finalize(doc, results, pdf_data)


def finalize(doc: Document, results: dict, pdf_data: bytes | None) -> dict:
    """Attach bboxes for PDF hits. PII gets bboxes for every match (redaction-ready)."""
    if pdf_data and doc.format == "PDF":
        for name, r in results.items():
            if not (r.get("grounded") and r.get("page_number")):
                continue
            try:
                if r.get("source") == "pii" and r.get("matches"):
                    boxes = []
                    for m in r["matches"]:
                        hit = grounding.locate(m, doc.pages)
                        if hit:
                            boxes.extend(highlight.find_bboxes(
                                pdf_data, hit["page_number"], m))
                    r["bboxes"] = boxes
                elif r.get("verbatim"):
                    r["bbox"] = highlight.find_bboxes(
                        pdf_data, r["page_number"], r["verbatim"])
            except Exception:
                pass
    grounded = sum(1 for r in results.values() if r.get("grounded"))
    return {"fields": results,
            "meta": {"format": doc.format, "pages": len(doc.pages),
                     "grounding_rate": f"{grounded}/{len(results)}"}}
