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

_STATE_WORDS = ("state", "province", "commonwealth", "district", "republic", "federal")


def _ed1(a: str, b: str) -> bool:
    """One insertion, deletion, or substitution apart (typo/OCR tolerance)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long = (a, b) if la < lb else (b, a)
    return any(short == long[:i] + long[i + 1:] for i in range(len(long)))


def clean_jurisdiction(raw: str | None) -> str | None:
    """Trim a captured jurisdiction: cut suffixes, keep multi-word wholes."""
    if not raw:
        return None
    aliases = {"prc": "People's Republic of China", "usa": "United States",
               "uk": "United Kingdom", "u.s.": "United States", "u.k.": "United Kingdom"}
    demonyms = {"italian": "Italy", "english": "England", "french": "France",
                "german": "Germany", "spanish": "Spain", "dutch": "Netherlands",
                "chinese": "China", "japanese": "Japan", "canadian": "Canada",
                "australian": "Australia", "indian": "India", "brazilian": "Brazil",
                 "mexican": "Mexico", "russian": "Russia", "israeli": "Israel",
                 "colombian": "Colombia"}
    g = _re.sub(r"\s*[,;].*$", "", raw).strip()
    if g.lower().strip(" .") in aliases:
        return aliases[g.lower().strip(" .")]
    if g.lower().strip(" .") in demonyms:
        return demonyms[g.lower().strip(" .")]
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
    # "State of X" the patterns didn't consume (typo: "Sate of Colorado"):
    # drop the state-word, keep the jurisdiction.
    if (len(parts) >= 3 and parts[1].lower() == "of"
             and (parts[0].lower() in _STATE_WORDS
                  or (len(parts[0]) >= 3 and any(_ed1(parts[0].lower(), s) for s in _STATE_WORDS)))):
         parts = parts[2:]
         if not parts:
             return None
    out = []
    for piece in parts:
        if piece.lower().strip(".,") in _JUR_STOP:
            break
        out.append(piece)
    val = " ".join(out)
    if not val:
        return None
    # proper-noun shape: every word capitalized or a small connector;
    # kills "ECOPETROL found in", lone "that"/"any", stray verbs
    connectors = {"of", "and", "the", "de", "la", "du", "der", "van", "von",
                  "di", "da", "le", "les", "el", "al"}
    for w in val.split():
        core = w.strip(".,;:()\"'")
        if not core:
            continue
        if core[0].isupper() or "'" in core or core.lower().startswith("mc"):
            continue
        if core.lower() in connectors:
            continue
        return None
    return val.title() if val.isupper() else val


_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
              "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
              "twelve": "12", "twenty": "20", "thirty": "30",
              "forty": "40", "sixty": "60", "ninety": "90"}


def _tidy_period(v: str | None) -> str | None:
    """Canonicalize a captured renewal region; truths favor digits ("12 months")."""
    if not v:
        return None
    v = v.replace("-", " ")
    v = _re.sub(r"\s+(terms?|periods?)\s*$", "", v, flags=_re.I).strip()
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", v):
        return "perpetual"
    m = _re.search(r"(?i)\b(successive\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|thirty|forty|sixty|ninety|\d+)(?:\s*\(\d+\))?\s*(years?|months?|days?)\b", v)
    if not m:
        return None
    succ, num, unit = m.group(1), m.group(2), m.group(3)
    pre = _re.search(r"(?i)\b(\w+)\s+successive\b", v)
    cnt = None
    if pre and pre.group(1).lower() not in ("for", "of", "and", "the", "to", "in", "on",
                                             "a", "an", "per", "each", "or", "nor", "successive"):
        cnt = pre.group(1)
    num = _NUM_WORDS.get(num.lower(), num)
    base = "year" if unit.lower().startswith("year") else ("month" if unit.lower().startswith("month") else "day")
    unit = base if num == "1" else base + "s"
    parts = ([cnt] if cnt else []) + ([succ.strip()] if succ else []) + [f"{num} {unit}"]
    return " ".join(parts).strip() or None


def clean_renewal(raw: str | None) -> str | None:
    """Extract a renewal period from a capture, or None (initial-term-only sections null out)."""
    if not raw:
        return None
    if _re.fullmatch(r"(?i)\s*perpetu\w*\s*", raw):
        return "perpetual"
    return _tidy_period(raw)


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
         r"governed\s+by\s+(?:the\s+)?(?!(?i:the|substantive|applicable|internal|exclusive|federal|such)\b)((?-i:[A-Z])[A-Za-z'\u2019\-]*(?:\s+(?:of\s+)?[A-Z][A-Za-z'\u2019\-]*){0,2})\s+laws?\b",
         r"laws?\s+of\s+(?:the\s+)?United\s+States(?:\s+of\s+America)?\s+and\s+of\s+the\s+(?:State|Commonwealth)\s+of\s+([A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,1})",
         r"laws?\s+of\s+the\s+(?:State|Commonwealth)\s+of\s+([A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,1})\s+and\s+of\s+(?:the\s+)?United\s+States",
         r"(?:laws?\s+of)\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
         r"governed\s+by\s+(?:and\s+)?construed\s+[^\n,;]{0,60}?laws?\s+of\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
         r"construed\s+[^\n,;]{0,60}?laws?\s+of\s+(?:(?:the|internal|exclusive|substantive)\s+)?(?:(?:State|Province|Commonwealth)\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z'\u2019\-]*)){0,3})",
        r"subject\s+to\s+(?:the\s+)?(?:application\s+of\s+)?(?:the\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+(?:of\s+)?[A-Z][A-Za-z'\u2019\-]*){0,2})\s+[Ll]aw\b",
         r"(?:regulations|rules)\s+of\s+([A-Z][A-Za-z'\u2019\-]*)\s+private\s+law\b",
         r"courts?\s+(?:located\s+)?in\s+[A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2}\s*,\s*(?:the\s+)?(?:state\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2})",
         r"jurisdiction\s+and\s+venue\s+(?:shall\s+be\s+)?in\s+[A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2}\s*,\s*(?:the\s+)?(?:state\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2})",
         r"(?:arbitrat\w+|disput\w+).{0,100}?\bin\s+[A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2}\s*,\s*(?:the\s+)?(?:state\s+of\s+)?([A-Z][A-Za-z'\u2019\-]*(?:\s+[A-Z][A-Za-z'\u2019\-]*){0,2})",
     ],
    "reject": r"(respective jurisdiction|any\s+(country|governmental authority)|any\s+other|this\s+or\s+any|such\s+jurisdiction|^any$)",
     "clean": clean_jurisdiction,
     "strip": ["and", "the", "of", "federal", "as"],
     "value_first": True,
     "headings": ["governing law"],
    "couple": [r"governed\s+by.{0,80}?laws?\s+of", r"laws?\s+of\s+(?:the\s+)?(?:State|Province|Commonwealth|District|Republic)\s+of"],
     "demote": [r"incorporat\w*", r"\borganiz\w+", r"formed\s+under", r"principal\s+place", r"\baddress\b", r"notice\s+(address|to)", r"for\s+all\s+purposes", r"export\s+(control|laws|compliance)", r"import\s+laws"],
    "resolve": {"triggers": [r"thereof", r"thereunder", r"therein"],
                "patterns": [r"(?:in|of)\s+the\s+State\s+of\s+([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})"]}},
    {"name": "termination_for_convenience", "strategy": "local", "section": True,
     "hint": "termination section: numbered/article/lettered heading + notice body",
     "anchors": ["termination", "term and termination", "termination rights",
                 "effect of termination", "cancellation"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": r"(?i)this termination agreement|termination agreement (represents|shall|may)",
     "reassemble": False,
     "member": r"(?i)\bterminat\w*\b.*\b(notice|days|written|convenience|without cause|sole discretion|at any time)\b",
     "qualify": r"(?i)(convenience|without cause|at its option|sole discretion|at any time|for any reason|without reason|upon (?:\S+\s+){0,4}?(days?|months?)'?s?\s+(?:prior\s+)?written\s+notice|on (?:\S+\s+){0,4}?(days?|months?)'?s?\s+(?:prior\s+)?written\s+notice)",
     "qualify_strong": r"(?i)(convenience|without cause|for any reason|at (its )?will|for no reason|without reason)",
     "disqualify": r"(?i)(effects?\s+of\s+terminat|consequences?\s+of|surviv\w*|shall\s+not\s+relea|shall\s+not\s+relie|for\s+cause|terminat\w+\s+(for|upon).{0,40}?(breach|default)|breach.{0,40}?terminat|insolven|deadlock|disagre|exercis\w*\s+\w+\s+decision|decision[\s-]making|failure\s+to\s+(agree|cure|perform|pay)|cure\s+period)",
     "normalize": None,
     "retrieve": ["terminat", "convenience", "without cause", "30 days", "written notice"]},
    {"name": "renewal_term", "strategy": "local", "section": True,
     "hint": "renewal section: auto-renewal and successive periods",
     "anchors": ["renewal", "renewal term", "successive", "auto-renew", "initial term",
                 "term", "initial term", "effective date and term"],
     "heading": None,
     "exclude": None,
     "reassemble": False,
     "member": r"(?i)\b(renew\w*|extension|extend\w*|successive|auto-?renew\w*|perpetu\w*)\b.*\b(successive|automatic|period|years?|months?|days?|extend|initial term|perpetual)\b",
     "qualify": r"(?i)(successive|automatic|perpetual|initial term|\d+\s*(year|month|day)|renewal term)",
     "normalize": r"((?:(?!(?:for|of|and|the|to|in|on|a|an|per|each)\s)\w+\s+)?successive\s+[A-Za-z0-9\'\u2019\-]+(?:\s+[A-Za-z0-9\'\u2019\-]+){0,1}\s*(?:year|month)s?)",
     "normalize_alt": [
         r"(?:renew\w*|auto[\s-]*renew\w*|successive|extend\w*|renewal)(?:(?!\binitial\s+term\b)[\s\S]){0,120}?((?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|thirty|forty|sixty|ninety|\d+)(?:\s*\(\d+\))?\s*(?:years?|months?))",
         r"\b(perpetu\w*)",
     ],
     "clean": clean_renewal,
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
