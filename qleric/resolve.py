"""Operative resolution, v2 + cross-doc renewal (L2).

Takes docs in precedence order (base first, amendments after) and returns
the operative value for one field plus its derivation chain. Adjacent
duplicate values collapse. Undated conflicting amendments abstain.
When the field carries a compute hook, a cross-doc term computation
(initial term + renewal count, starts from the docs) may override
start-echoes and single-doc derivations — but never a stated end date.
"""
from __future__ import annotations

import re as _re

from qleric import grounding, query
from qleric.packs import CONTRACT_FIELDS
from qleric.primitives import period as _P
from qleric.primitives import date as _D

_DATED = _re.compile(r"(?im)^\s*dated\s+.+")
_META_HEAD = _re.compile(r"(?i)\b(?:dated|date)\b[^.]{0,30}\d")
_OPERATIVE_NOUN = _re.compile(r"(?i)expir|effective|terminat|matur|end\s+date")


def _same(a: str, b: str) -> bool:
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())


def _parse(v: str | None):
    try:
        return _D.parse_date(v) if v else None
    except Exception:
        return None


_DATE_FIELDS = {f["name"]: f for f in CONTRACT_FIELDS
                if f["name"] in ("agreement_date", "effective_date")}


def resolve(docs: list, field: dict, roles: list[str | None] | None = None) -> dict:
    """Resolve the operative value for `field` across `docs` in order.

    `roles` (parallel to docs) marks standing: doc 0 is the base; only
    amendment-role docs participate beyond it. Exhibits and junk docs are
    never operative evidence. Omitted roles preserve legacy behavior
    (every non-base doc amends).
    """
    if roles is None:
        roles = ["base"] + ["amend"] * (len(docs) - 1)
    texts = ["\n".join(p.text for p in d.pages) for d in docs]
    qfields = [field] + [_DATE_FIELDS["agreement_date"], _DATE_FIELDS["effective_date"]]
    starts: list[str | None] = []
    hits = []
    for i, doc in enumerate(docs):
        res = query(doc, qfields, None, deep=False)
        got = (res["fields"] or {}).get(field["name"]) or {}
        agree = ((res["fields"] or {}).get("agreement_date") or {}).get("value")
        eff = ((res["fields"] or {}).get("effective_date") or {}).get("value")
        starts.append(agree or eff)
        if got.get("value") is not None and got.get("grounded"):
            verb = got.get("verbatim") or ""
            if verb and not grounding.locate(verb, doc.pages):
                continue  # unlocatable span is not evidence
            if field.get("compute") and _META_HEAD.search(verb) \
                    and not _OPERATIVE_NOUN.search(verb):
                continue  # date/dated headers are metadata, never operative content
            if i > 0 and not (roles[i] or "").startswith("amend"):
                continue  # exhibits and junk docs are never operative evidence
            hits.append({"doc": i, "value": got["value"], "verbatim": verb,
                         "dated": bool(_DATED.search(texts[i])),
                         "computed": bool(got.get("computed")),
                         "mechanisms": got.get("_mechanisms", [])})
    # Adjacent duplicates collapse: a re-filed identical amendment adds
    # no information. Non-adjacent repeats (reverts) keep the full chain.
    deduped = [hits[0]] if hits else []
    for h in hits[1:]:
        if _same(h["value"], deduped[-1]["value"]):
            continue
        deduped.append(h)
    hits = deduped
    if not hits:
        # No per-doc value at all: a cross-doc computation may still resolve.
        computed = _P.renewal_end(texts, starts, roles) if field.get("compute") else None
        if computed:
            return _computed_result(computed, [], docs)
        return {"value": None, "grounded": False, "chain": [],
                "superseded": [], "note": "no grounded value in any doc"}
    # Conflict needs 2+ AMENDMENT hits that disagree with no precedence
    # between them. Base-vs-amend always resolves by order (supersession is
    # definitional); a lone undated amend is a move, not a conflict.
    amend_hits = [h for h in hits if (roles[h["doc"]] or "").startswith("amend")]
    if (len(amend_hits) >= 2 and not _same(amend_hits[-1]["value"], amend_hits[-2]["value"])
            and not amend_hits[-1]["dated"] and not amend_hits[-2]["dated"]):
        earlier, last = amend_hits[-2], amend_hits[-1]
        return {"value": None, "grounded": False,
                "chain": [],
                "alternatives": [
                    {"doc": earlier["doc"], "value": earlier["value"],
                     "verbatim": earlier["verbatim"]},
                    {"doc": last["doc"], "value": last["value"],
                     "verbatim": last["verbatim"]}],
                "superseded": [h["value"] for h in hits if h not in (earlier, last)],
                "note": "conflicting undated amendments: abstained",
                "mechanisms": ["operative-abstain"]}
    # Count conflicts: undated amends asserting different renewal counts.
    # Like value conflicts, recency cannot decide — abstain with both cites.
    # Gated on compute: counts only matter where renewal_end would use them.
    if field.get("compute"):
        by_count: dict[int, list[tuple[int, str]]] = {}
        for i, text in enumerate(texts):
            if i == 0 or not (roles[i] or "").startswith("amend") or _DATED.search(text):
                continue
            for k, sent in _P.find_counts(text):
                by_count.setdefault(k, []).append((i, sent))
        if len(by_count) >= 2:
            alts = [{"doc": di, "verbatim": s} for k in sorted(by_count)
                    for di, s in by_count[k][:1]]
            return {"value": None, "grounded": False,
                    "chain": [],
                    "alternatives": alts,
                    "superseded": [h["value"] for h in hits],
                    "note": "conflicting renewal counts: abstained",
                    "mechanisms": ["operative-abstain"]}
        computed = _P.renewal_end(texts, starts, roles)
        if computed is not None:
            value, cites = computed
            if all(grounding.locate(c["verbatim"], docs[c["doc"]].pages) for c in cites):
                over = all(h.get("computed") or _is_start(h["value"], starts) for h in hits)
                if over:
                    chain = [{"doc": c["doc"], "verbatim": c["verbatim"]} for c in cites]
                    return {"value": value, "grounded": True, "chain": chain,
                            "superseded": list(dict.fromkeys(
                                [h["value"] for h in hits if h["value"] != value])),
                            "note": "computed across docs: initial term + renewal count",
                            "computed": True, "mechanisms": ["operative-computed"]}
    operative = hits[-1]
    return {"value": operative["value"], "grounded": True,
            "chain": [{"doc": h["doc"], "value": h["value"],
                       "verbatim": h["verbatim"]} for h in hits],
            "superseded": [h["value"] for h in hits[:-1]],
            "mechanisms": ["operative-latest"] + sorted(operative["mechanisms"])}


def _is_start(value: str | None, starts: list[str | None]) -> bool:
    """A hit that merely echoes a start date carries no operative content."""
    v = _parse(value)
    return v is not None and any(v == _parse(s) for s in starts if s)


def _computed_result(computed, docs: list) -> dict:
    value, cites = computed
    if not all(grounding.locate(c["verbatim"], docs[c["doc"]].pages) for c in cites):
        return {"value": None, "grounded": False, "chain": [],
                "superseded": [], "note": "computed but uncitable"}
    chain = [{"doc": c["doc"], "verbatim": c["verbatim"]} for c in cites]
    return {"value": value, "grounded": True, "chain": chain,
            "superseded": [], "note": "computed across docs: initial term + renewal count",
            "computed": True, "mechanisms": ["operative-computed"]}
