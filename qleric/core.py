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
            span = local.find_section(doc.body_text, f.get("anchors", []),
                                      member=f.get("member"))
            if span:
                value = local.normalize(f.get("normalize"), span, f.get("strip"))
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
                best = local.find_span(doc.body_text, f.get("anchors", []),
                                       pattern=f.get("normalize"), match_first=True,
                                       reject=f.get("reject"))
                if best:
                    v0 = local.normalize(f.get("normalize"), best, f.get("strip"))
                    rej = f.get("reject")
                    if v0 is not None and not (rej and _re.search(rej, v0, _re.IGNORECASE)):
                        scored.append((101.0, f["name"], best))
                continue
            for span in local.candidates(doc.body_text):
                s = local.score(span, f.get("anchors", []))
                norm = f.get("normalize")
                if norm and s > 30.0 and _re.search(norm, span, _re.IGNORECASE):
                    s += 40.0  # anchor-proximate value: paragraph-embedded dates/law
                if _re.match(r"\s*\d+\.\s+[A-Z][A-Z \-/&]+", span):
                    s += 25.0  # numbered section heading in span: clause authority
                for h in f.get("headings", []):
                    if h.lower() in span.lower():
                        s += 50.0  # field's own section heading present: strongest signal
                        break
                if s > 55.0:
                    scored.append((s, f["name"], span))
        scored.sort(reverse=True)
        claimed_values: set[str] = set()
        for _, name, span in scored:
            if name in results:
                continue
            f = next(x for x in pending if x["name"] == name)
            value = local.normalize(f.get("normalize"), span, f.get("strip"))
            if value is None:
                continue  # anchor matched but no value present (template/placeholder)
            rej = f.get("reject")
            if rej and _re.search(rej, value, _re.IGNORECASE):
                continue  # known trap shape (year range as phone): skip span
            if value in claimed_values:
                continue  # same value already claimed by a higher scorer
            hit = grounding.locate(span.splitlines()[0], doc.pages) or {}
            results[name] = {"value": value, "verbatim": span.strip(),
                             **hit, "grounded": True, "source": "local"}
            claimed_values.add(value)
    llm_fields = [f for f in fields
                  if f["name"] not in results
                  and (deep or f.get("strategy", "llm") == "llm")]
    if llm_fields:  # Small model first; escalate flagged fields that miss or unground
        _run_lm_pass(doc, llm_fields, results, model=None)
        big_fields = [f for f in llm_fields if f.get("escalate")
                      and not results.get(f["name"], {}).get("grounded")]
        if big_fields:
            import os as _os
            big_model = _os.getenv("MODEL_BIG", "")
            if big_model:
                _run_lm_pass(doc, big_fields, results, model=big_model, tier="big")
    else:  # keyless local-only: report misses honestly
        for f in fields:
            results.setdefault(f["name"], {"value": None, "grounded": False,
                                           "source": f.get("strategy", "llm"),
                                           "note": "no local match; needs LLM (deep=true or key)"})
    for f in fields:  # backfill: every declared field appears in output
        if f["name"] not in results:
            results[f["name"]] = {"value": None, "grounded": False,
                                  "source": f.get("strategy", "llm"),
                                  "note": "no match at any tier"}
    return finalize(doc, results, pdf_data)


def _targeted_context(doc: Document, llm_fields: list[dict], budget: int = 12000) -> str:
    """Clause-targeted retrieval: keyword windows per field, not the full dump.

    Each llm field declares retrieval keywords (default: hint words). Top
    windows go in; the full document is fallback when nothing scores.
    """
    import re as _re
    windows: list[tuple[float, str]] = []
    for f in llm_fields:
        keys = f.get("retrieve") or [w for w in re_words(f.get("hint", "")) if len(w) > 3]
        for page in doc.pages:
            if page.sparse:
                continue
            for m in _re.finditer(r".{0,600}(?:" + "|".join(map(_re.escape, keys)) + r").{0,600}",
                                  page.text, _re.IGNORECASE | _re.DOTALL):
                seg = " ".join(m.group(0).split())
                score = sum(k.lower() in seg.lower() for k in keys)
                windows.append((score, f"[Page {page.number}] {seg}"))
    windows.sort(reverse=True)
    out, total = [], 0
    for _, w in windows:
        if total + len(w) > budget:
            break
        out.append(w)
        total += len(w)
    if not out:  # nothing scored: full doc fallback (capped)
        out = [f"[Page {p.number}]\n{p.text}" for p in doc.pages if not p.sparse]
        return "\n\n".join(out)[:100_000]
    return "\n\n---\n\n".join(out)


def re_words(s: str) -> list[str]:
    import re as _re
    return _re.findall(r"[A-Za-z]{4,}", s)


def _run_lm_pass(doc: Document, llm_fields: list[dict], results: dict,
                 model: str | None = None, tier: str = "small") -> None:
    """Single LLM pass over fields; ground each claim locally. Mutates results."""
    context = _targeted_context(doc, llm_fields)
    user = "FIELDS:\n" + "\n".join(f"- {f['name']}: {f.get('hint', '')}" for f in llm_fields)
    user += "\n\nDOCUMENT:\n" + context
    try:
        raw = chat(SYSTEM, user[:100_000], _schema_hint(llm_fields), model=model)
    except LMError as e:
        for f in llm_fields:  # keyless: report honestly instead of dropping
            results.setdefault(f["name"], {"value": None, "grounded": False,
                                           "source": f.get("strategy", "llm"),
                                           "note": str(e)})
        return
    for f in llm_fields:
        item = raw.get(f["name"], {}) if isinstance(raw, dict) else {}
        value, verbatim = item.get("value"), item.get("verbatim")
        hit = grounding.locate(verbatim, doc.pages) if verbatim else None
        if value and hit:
            results[f["name"]] = {"value": value, "verbatim": verbatim,
                                  **hit, "grounded": True, "source": f"llm-{tier}"}
        else:
            if tier == "big" or f["name"] not in results:
                results[f["name"]] = {"value": value, "verbatim": verbatim,
                                      "grounded": False, "source": f"llm-{tier}",
                                      "page_number": item.get("page_number")}


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
    meta: dict = {"format": doc.format, "pages": len(doc.pages),
                  "grounding_rate": f"{grounded}/{len(results)}"}
    try:
        from . import costs as _costs
        meta["cost"] = _costs.total()
    except Exception:
        pass
    return {"fields": results, "meta": meta}
