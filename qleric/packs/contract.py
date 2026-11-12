"""Contract pack: CUAD-aligned. Local anchors for dates/law, LLM for clauses.

Column mapping from CUAD master_clauses.csv: Agreement Date, Effective Date,
Expiration Date, Governing Law -> local spans. Termination For Convenience,
Renewal Term, Non-Compete, Exclusivity, Most Favored Nation -> llm with
escalate (small model first, MODEL_BIG on miss/ungrounded).
"""
from __future__ import annotations

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
     "normalize": r"(?:laws? of|State of|Province of|Commonwealth of)\s+(?:the\s+)?(?:State of\s+|Province of\s+|Commonwealth of\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)",
     "strip": ["and", "the", "of", "federal", "as"]},
    {"name": "termination_for_convenience", "strategy": "llm", "escalate": True,
     "hint": "can either party terminate for convenience? quote the clause",
     "retrieve": ["terminat", "convenience", "without cause", "30 days", "written notice"]},
    {"name": "renewal_term", "strategy": "llm", "escalate": True,
     "hint": "renewal or auto-renewal terms, quote the clause",
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
