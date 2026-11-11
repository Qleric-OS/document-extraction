"""Contract pack: CUAD-aligned. Local anchors for parties/dates/law, LLM for clauses.

Column mapping from CUAD master_clauses.csv: Parties, Agreement Date,
Effective Date, Expiration Date, Governing Law -> local spans.
Termination For Convenience, Renewal Term, Non-Compete, Exclusivity,
Most Favored Nation, No-Solicit, Non-Disparagement -> llm (clause judgment).
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
    {"name": "termination_for_convenience", "strategy": "llm",
     "hint": "can either party terminate for convenience? quote the clause"},
    {"name": "renewal_term", "strategy": "llm",
     "hint": "renewal or auto-renewal terms, quote the clause"},
    {"name": "non_compete", "strategy": "llm",
     "hint": "non-compete restrictions, quote the clause or null"},
    {"name": "exclusivity", "strategy": "llm",
     "hint": "exclusivity obligations, quote the clause or null"},
    {"name": "most_favored_nation", "strategy": "llm",
     "hint": "most favored nation clause, quote or null"},
]
