"""Contract pack: CUAD-aligned. Local anchors for dates/law, LLM for clauses.

Column mapping from CUAD master_clauses.csv: Agreement Date, Effective Date,
Expiration Date, Governing Law -> local spans. Termination For Convenience,
Renewal Term, Non-Compete, Exclusivity, Most Favored Nation -> llm with
escalate (small model first, MODEL_BIG on miss/ungrounded).

Governing-law jurisdiction grammar is truth-mined (see
evals/law_grammar_coverage.md): 409/433 CUAD answers exact, 0 real misses.
"""
from __future__ import annotations

import re as _re

# Multi-word jurisdictions from CUAD truth (not guessed). Used by
# clean_jurisdiction() to keep "England and Wales" whole and cut
# "Ontario and ..." trailing noise.
MULTI_JURISDICTIONS = frozenset({
    "New York", "New Jersey", "New Mexico", "New Hampshire",
    "North Carolina", "South Carolina", "North Dakota", "South Dakota",
    "Hong Kong", "Costa Rica", "Sri Lanka", "Dominican Republic",
    "South Africa", "South Korea", "New Zealand", "Papua New Guinea",
    "Saudi Arabia", "United States", "United Kingdom", "England and Wales",
    "District of Columbia", "British Columbia", "People's Republic of China",
    "Nova Scotia", "Rhode Island", "West Virginia", "Czech Republic",
    "Federal Republic of Germany", "Republic of Kazakhstan",
    "Republic of South Africa", "El Salvador", "Burkina Faso", "Sierra Leone",
})

_JUR_STOP = frozenset({
    "and", "the", "of", "federal", "as", "applicable", "without", "internal",
    "exclusive", "substantive", "laws", "law", "state", "province",
    "commonwealth", "district", "republic",
})


def clean_jurisdiction(raw: str | None) -> str | None:
    """Trim a captured jurisdiction: cut suffixes, keep multi-word wholes."""
    if not raw:
        return None
    g = _re.sub(r"\s*[,;].*$", "", raw).strip()
    parts = g.split()
    while parts and parts[0].lower() in ("and", "construed", "governed"):
        parts.pop(0)
    if not parts:
        return None
    low = {j.lower(): j for j in MULTI_JURISDICTIONS}
    joined = " ".join(parts)
    if joined.lower() in low:
        return low[joined.lower()]
    for length in (4, 3, 2):
        if len(parts) >= length:
            cand = " ".join(parts[:length])
            if cand.lower() in low:
                return low[cand.lower()]
    out = []
    for piece in parts:
        if piece.lower().strip(".,") in _JUR_STOP:
            break
        out.append(piece)
    return " ".join(out) or None


FIELDS = [
    {"name": "agreement_date", "strategy": "local", "hint": "date the agreement was signed",
     "anchors": ["agreement date", "dated as of", "dated", "date of agreement",
                 "entered into", "effective date"],
     "normalize": r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[A-Z][a-z]+ [0-9]{1,2}(st|nd|rd|th)?\s*,?\s*20[0-9]{2}|[0-9]{1,2}(st|nd|rd|th) day of [A-Z][a-z]+,? 20[0-9]{2})"},
    {"name": "effective_date", "strategy": "local", "hint": "when the agreement takes effect",
     "anchors": ["effective date", "commence", "term shall begin", "in effect"],
     "normalize": r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[A-Z][a-z]+ [0-9]{1,2},? 20[0-9]{2})"},
    {"name": "expiration_date", "strategy": "local", "hint": "when the agreement ends",
     "anchors": ["expiration date", "terminate on", "expires", "end of the term", "remain in effect until"],
     "normalize": r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[A-Z][a-z]+ [0-9]{1,2},? 20[0-9]{2})"},
    {"name": "governing_law", "strategy": "local", "hint": "governing law jurisdiction",
     "anchors": ["governing law", "governed by", "laws of the",
                 "construed in accordance with"],
     "normalize": r"(?:laws?\s+of)\s+(?:the\s+)?((?:Federal\s+)?Republic\s+of\s+[A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2})",
     "normalize_alt": [
         r"governed\s+by\s+([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of\s+)?[A-Z][A-Za-z'\u2019\-]*){0,2})\s+law\b",
         r"(?:laws?\s+of)\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
         r"governed\s+by\s+(?:and\s+)?construed\s+[^\n,;]{0,60}?laws?\s+of\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
         r"construed\s+[^\n,;]{0,60}?laws?\s+of\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
     ],
     "clean": clean_jurisdiction,
     "strip": ["and", "the", "of", "federal", "as"],
     "value_first": True,
     "headings": ["governing law"],
     "couple": [r"governed\s+by.{0,80}?laws?\s+of", r"laws?\s+of\s+(?:the\s+)?(?:State|Province|Commonwealth|District|Republic)\s+of"],
     "demote": [r"incorporat\w*", r"\borganiz\w+", r"formed\s+under", r"principal\s+place", r"\baddress\b", r"notice\s+(address|to)", r"for\s+all\s+purposes"]},
    {"name": "termination_for_convenience", "strategy": "local", "section": True,
     "hint": "termination section: numbered/article/lettered heading + notice body",
     "anchors": ["termination", "term and termination", "termination rights",
                 "effect of termination", "cancellation"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": r"(?i)this termination agreement|termination agreement (represents|shall|may)",
     "reassemble": False,
     "member": r"(?i)\bterminat\w*\b.*\b(notice|days|written|convenience|without cause|sole discretion|at any time)\b",
     "qualify": r"(?i)(convenience|without cause|at its option|sole discretion|at any time|for any reason)",
     "normalize": None,
     "retrieve": ["terminat", "convenience", "without cause", "30 days", "written notice"]},
    {"name": "renewal_term", "strategy": "local", "section": True,
     "hint": "renewal section: auto-renewal and successive periods",
     "anchors": ["renewal", "renewal term", "successive", "auto-renew", "initial term",
                 "term", "initial term", "effective date and term"],
     "heading": None,
     "exclude": None,
     "reassemble": False,
     "member": r"(?i)\brenew\w*\b.*\b(successive|automatic|period|year|extend|initial term)\b",
     "qualify": r"(?i)(successive|automatic|perpetual|initial term|\d+\s*(year|month)|renewal term)",
     "normalize": None,
     "retrieve": ["renew", "successive", "auto-renew", "initial term", "extend"]},
    {"name": "non_compete", "strategy": "llm", "escalate": True,
     "hint": "non-compete restrictions, quote the clause or null",
     "retrieve": ["compete", "competitive", "restrictive covenant", "solicit", "covenant not to"]},
    {"name": "exclusivity", "strategy": "llm", "escalate": True,
     "hint": "exclusivity obligations, quote the clause or null",
     "retrieve": ["exclusiv", "sole", "only", "solely"]},
    {"name": "most_favored_nation", "strategy": "llm", "escalate": True,
     "hint": "most favored nation clause, quote or null",
     "retrieve": ["favored nation", "MFN", "most favorable", "no less favorable"]},
]
