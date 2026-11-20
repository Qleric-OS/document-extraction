"""Contract pack: CUAD-aligned. Local anchors for dates/law, LLM for clauses.

Column mapping from CUAD master_clauses.csv: Agreement Date, Effective Date,
Expiration Date, Governing Law -> local spans. Termination For Convenience,
Renewal Term, Non-Compete, Exclusivity, Most Favored Nation -> llm with
escalate (small model first, MODEL_BIG on miss/ungrounded).

Governing-law jurisdiction grammar is truth-mined (see
evals/law_grammar_coverage.md): 409/433 CUAD answers exact, 0 real misses.
"""
from __future__ import annotations

import functools
import re as _re
from qleric.primitives.entity import _ed1, is_proper_noun_phrase
from qleric.primitives.period import clean_renewal, clean_notice
from qleric.primitives.obligation import (
    DISQUALIFY as P5_DISQUALIFY,
    STRONG as P5_STRONG,
    WEAK as P5_WEAK,
    CATEGORIES as P5_CATEGORIES,
    find_unheaded as P5_find_unheaded,
    clean_termination,
    verdict_for,
)

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
    if not is_proper_noun_phrase(val):
        return None
    return val.title() if val.isupper() else val

_NOTICE_NUM = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
               r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
               r"thirty|forty|fifty|sixty|eighty|ninety|\d+)")
# Duration core. Intra-duration whitespace is spaces/tabs only: a number and its
# unit split across lines ("successive one\\ndays...") must not fuse into "1 day".
_NOTICE_DUR = (_NOTICE_NUM + r"(?:[ \t]*\(\d+\))?[ \t]*-?[ \t]*"
               r"(?:days?|months?|weeks?|years?)(?:'s?)?")
_NOTICE_NW = r"(?:notic\w*|notif\w*)"
_NOTICE_TAIL = (r"(?:prior\s+|before\s+|preceding\s+|previous\s+|advance\s+|following\s+"
                r"|of\s+the\s+(?:conclusion|end)\b|to\s+the\s+end)")
_NOTICE_VETO = r"(?![^.]*?(?:breach|cure|cured|curing|default\w*|failure\s+to))"
_NOTICE_ATAR = r"(?![^.]*?\bat\s+any\s+time\b)"
_NOTICE_REN = (r"(?:renew\w*|non-?renewal|expir\w*|extension|extend\w*|evergreen|"
               r"terms?\b)")
_NOTICE_AUTOREN = (r"(?:automat\w*\s+renew\w*|renew\w*\s+automat\w*|auto-?renew\w*|"
                   r"evergreen)")
_NOTICE_NONREN = r"(?:non-?renew\w*|not\s+to\s+renew)"
_NOTICE_SH1 = ("(" + _NOTICE_DUR + r")\s*" + _NOTICE_TAIL + r"?(?:written\s+)?"
               + _NOTICE_NW)
_NOTICE_SH2 = (_NOTICE_NW + r"[^.]{0,120}?(?:at\s+least\s+|not\s+less\s+than\s+|"
               r"no\s+fewer\s+than\s+)?(" + _NOTICE_DUR + r")\s*" + _NOTICE_TAIL)
_NOTICE_SH2B = (_NOTICE_NW + r"[^.]{0,120}?(?:of\s+not\s+less\s+than\s+|of\s+at\s+least\s+)"
                r"(" + _NOTICE_DUR + r")\b")
# Tier 0: the canonical non-renewal clause lives in the auto-renewal sentence.
# Tier 1: renewal/term-scoped notice, excluding at-any-time (TFC) grants.
# Tier 2: any termination notice (general-termination truths like Euromedia).
_NOTICE_T0 = (_NOTICE_ATAR + _NOTICE_VETO + r"(?=[^.]*?" + _NOTICE_AUTOREN + r")"
              r"(?=[^.]*?" + _NOTICE_NONREN + r")"
              r"[^.]*?(" + _NOTICE_DUR + r")\s*" + _NOTICE_TAIL)
_NOTICE_MAIN = (_NOTICE_ATAR + _NOTICE_VETO + r"(?=[^.]*?" + _NOTICE_REN + r")"
                r"[^.]*?(?:" + _NOTICE_SH1 + r"|" + _NOTICE_SH2 + r"|"
                + _NOTICE_SH2B + r")")
_NOTICE_ALT = (_NOTICE_VETO + r"[^.]*?(?:" + _NOTICE_SH1 + r"|" + _NOTICE_SH2 + r"|"
               + _NOTICE_SH2B + r")")
_RENEW_VETO = r"(?![^.]*?(?:breach|cure|cured|curing|default\w*|failure\s+to))"
_RENEW_PRE = r"(?:(?!(?:for|of|and|the|to|in|on|a|an|per|each|or|nor|successive)\s)\w+\s+)?"
_RENEW_SPECIAL = r"(?:annual(?:ly)?\s+(?:periods?|terms?)|month\s*(?:-\s*)?to\s*(?:-\s*)?month)"
_RENEW_DUR = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
              r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
              r"thirty|forty|fifty|sixty|eighty|ninety|\d+)(?:[ \t]*\(\d+\))?[ \t]*-?"
              r"[ \t]*(?:days?|months?|weeks?|years?)(?:'s?)?")
# Renewal needs a license-area anchor nearby for open-ended grants
# ("in perpetuity", "unlimited terms") to count as renewal periods.
_RENEW_CTX = r"(?=[^.]*?(?:renew\w*|extend\w*|successive|evergreen|auto\w*))"
_RENEW_MAIN = (_RENEW_VETO
               + r"((?:unlimited\s+(?:number\s+of\s+)?(?:successive\s+)?(?:terms?|renewals?|periods?))"
               + r"|(?:" + _RENEW_PRE
               + r"successive\s+(?:[A-Za-z0-9'\u2019\-]+\s+){0,3}?" + _RENEW_DUR + r")"
               + r"|(?:" + _RENEW_CTX + r"(perpetu\w*)))")
_RENEW_ALT = [(_RENEW_VETO + r"(" + _RENEW_PRE
               + r"(?:automat\w*\s+renew\w*|renew\w*\s+automat\w*|auto-?renew\w*|renew\w*|successive|extend\w*|renewal)"
               + r"(?:(?!\binitial\s+term\b)[\s\S]){0,120}?" + _RENEW_DUR + r")"),
              r"(" + _RENEW_SPECIAL + r")",
              r"\b(perpetu\w*)"]
FIELDS = [
    {"name": "agreement_date", "strategy": "local", "hint": "date the agreement was signed",
     "anchors": ["agreement date", "dated as of", "dated", "date of agreement",
                 "entered into", "effective date"],
     "normalize": r"((?<![\d/\-])(?:0?[1-9]|1[0-2])[/\-.][0-9]{1,2}[/\-.](?:\d{2}|(?:19|20)\d{2})(?![\d/\-])|[A-Z][a-z]+\.? [0-9]{1,2}(?:st|nd|rd|th)?\s*,?\s*(?:19|20)[0-9]{2}|[0-9]{1,2}(?:st|nd|rd|th) day of [A-Z][a-z]+\.?\,?\s*(?:19|20)[0-9]{2})",
     "reject": r"^\d{1,2}\.\d{1,2}\.\d{2}$",
     "reject_span": r"(?i)^\s*source:",
     "value_first": True},
    {"name": "effective_date", "strategy": "local", "hint": "when the agreement takes effect",
     "anchors": ["effective date", "commence", "term shall begin", "in effect"],
     "normalize": r"((?<![\d/\-])(?:0?[1-9]|1[0-2])[/\-.][0-9]{1,2}[/\-.](?:\d{2}|(?:19|20)\d{2})(?![\d/\-])|[A-Z][a-z]+\.? [0-9]{1,2},? (?:19|20)[0-9]{2})",
     "reject": r"^\d{1,2}\.\d{1,2}\.\d{2}$",
     "reject_span": r"(?i)^\s*source:",
     "value_first": True},
    {"name": "expiration_date", "strategy": "local", "hint": "when the agreement ends",
     "anchors": ["expiration date", "terminate on", "expires", "end of the term", "remain in effect until",
                 "perpetual"],
     "normalize": r"(\bperpetual\b|(?<![\d/\-])(?:0?[1-9]|1[0-2])[/\-.][0-9]{1,2}[/\-.](?:\d{2}|(?:19|20)\d{2})(?![\d/\-])|[A-Z][a-z]+\.? [0-9]{1,2},? (?:19|20)[0-9]{2})",
     "reject": r"^\d{1,2}\.\d{1,2}\.\d{2}$",
     "reject_span": r"(?i)^\s*source:",
     "value_first": True},
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
     # Discovery (find_section) uses qualify/disqualify below; verdict uses clean_termination (P5).
     # Keep both: keys guide WHICH span wins, P5 decides whether it grants.
     "qualify": "(?i)(" + P5_WEAK + ")",
     "qualify_strong": "(?i)(" + P5_STRONG + ")",
     "disqualify": "(?i)(" + P5_DISQUALIFY + ")",
     "normalize": None,
     "clean": clean_termination,
     "retrieve": ["terminat", "convenience", "without cause", "30 days", "written notice"]},
    {"name": "renewal_term", "strategy": "local", "section": True,
     "hint": "renewal section: auto-renewal and successive periods",
     "anchors": ["renewal", "renewal term", "successive", "auto-renew", "initial term",
                 "term", "initial term", "effective date and term"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(renew\w*|extension|extend\w*|successive|auto-?renew\w*|perpetu\w*)\b.*\b(successive|automatic|period|years?|months?|days?|extend|initial term|perpetual)\b|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|eighty|ninety|\d+)\b.{0,60}?\b(?:periods?|terms?|successive|renew\w*)\b|\b(?:periods?|terms?|successive|renew\w*)\b.{0,60}?\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|eighty|ninety|\d+)\b",
     "qualify": r"(?i)(successive|automatic|perpetual|unlimited|initial term|\d+\s*(year|month|day)|renewal term)",
     "normalize": _RENEW_MAIN,
     "normalize_alt": _RENEW_ALT,
     "clean": clean_renewal,
     "retrieve": ["renew", "successive", "auto-renew", "initial term", "extend"]},
    {"name": "notice_period_to_terminate_renewal", "strategy": "local", "section": True,
     "hint": "notice period to stop auto-renewal, e.g. 30 days prior written notice",
     "anchors": ["non-renewal", "nonrenewal", "notice", "automatic renewal", "evergreen",
                 "renewal", "expiration", "written notice", "termination",
                 "term and termination", "term", "notify", "notification"],
     "heading": None,
     "exclude": None,
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(renew\w*|non-?renewal|expir\w*|terminat\w*|cancel\w*|extension|extend\w*|evergreen|automat\w*|end\s+of\s+the)\b.{0,200}?\b(notic\w*|notif\w*)\b|\b(notic\w*|notif\w*)\b.{0,200}?\b(renew\w*|non-?renewal|expir\w*|terminat\w*|cancel\w*|extension|extend\w*)\b",
     "normalize": _NOTICE_T0,
     "normalize_alt": [_NOTICE_MAIN, _NOTICE_ALT],
     "clean": clean_notice,
     "retrieve": ["prior written notice", "days notice", "non-renewal", "not renew", "expire", "evergreen"]},
    {"name": "non_compete", "strategy": "local", "section": True,
     "hint": "non-compete restrictions, quote the clause or null",
     "anchors": P5_CATEGORIES["non_compete"]["anchors"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": None,
     "reassemble": False,
     "normalize": None,
     "clean": verdict_for("non_compete"),
     "fallback": functools.partial(P5_find_unheaded, category="non_compete"),
     "retrieve": ["compete", "competitive", "restrictive covenant", "solicit", "covenant not to"]},
    {"name": "no_solicit_employees", "strategy": "local", "section": True,
     "hint": "employee non-solicitation restrictions, quote the clause or null",
     "anchors": P5_CATEGORIES["no_solicit_employees"]["anchors"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": None,
     "reassemble": False,
     "normalize": None,
     "clean": verdict_for("no_solicit_employees"),
     "fallback": functools.partial(P5_find_unheaded, category="no_solicit_employees"),
     "retrieve": ["solicit", "recruit", "poach", "hire away", "personnel", "hire", "recruit"]},
    {"name": "no_solicit_customers", "strategy": "llm", "escalate": True,
     "hint": "customer non-solicitation restrictions, quote the clause or null",
     "retrieve": ["solicit customers", "solicit clients", "non-solicitation", "poach", "divert clients", "circumvent"]},
    {"name": "license_grant", "strategy": "local", "section": True,
     "hint": "license grant clause, quote the clause or null",
     "anchors": P5_CATEGORIES["license_grant"]["anchors"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": None,
     "reassemble": False,
     "normalize": None,
     "clean": verdict_for("license_grant"),
     "fallback": functools.partial(P5_find_unheaded, category="license_grant"),
     "retrieve": ["license", "grant of rights", "authorized use", "hereby grants"]},
    {"name": "exclusivity", "strategy": "llm", "escalate": True,
     "hint": "exclusivity obligations, quote the clause or null",
     "retrieve": ["exclusiv", "sole", "only", "solely"]},
    {"name": "most_favored_nation", "strategy": "local", "section": True,
     "hint": "most favored nation / parity pricing clause, quote the clause or null",
     "anchors": P5_CATEGORIES["most_favored_nation"]["anchors"],
     "heading": None,
     "exclude": None,
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(most\s+favou?r\w*|no\s+less\s+favou?r\w*|at\s+least\s+as\s+favou?r\w*|more\s+favou?r\w*|equal\s+to\s+or\s+more\s+favou?r|favou?red\s+nation|lowest\s+price|MFN)\b",
     "normalize": None,
     "clean": verdict_for("most_favored_nation"),
     "fallback": functools.partial(P5_find_unheaded, category="most_favored_nation"),
     "retrieve": ["favored nation", "MFN", "most favorable", "no less favorable", "lowest price", "most favored"]},
    {"name": "anti_assignment", "strategy": "local", "section": True,
     "hint": "anti-assignment restriction: consent required to assign, quote the clause or null",
     "anchors": P5_CATEGORIES["anti_assignment"]["anchors"],
     "heading": r"(?i)^\s*(\d+[\.\)]|article\s+\d+|section\s+\d+|[a-z]\.)\s*",
     "exclude": r"(?i)\bdefinitions?\b|capitalized\s+terms",
     "threshold": 10.0,
     "reassemble": True,
     "member": r"(?i)\b(?:assign\w*|delegat\w*)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|consent|without|neither|nor|no|approval)\b|\b(?:shall|will|may|must|agre\w*|consent|without|neither|nor|no|approval)\b.{0,120}?\b(?:assign\w*|delegat\w*)\b",
     "normalize": None,
     "clean": verdict_for("anti_assignment"),
     "fallback": functools.partial(P5_find_unheaded, category="anti_assignment"),
     "retrieve": ["assign", "consent to assign", "successors and assigns", "delegate", "without consent", "assignable"]},
    {"name": "covenant_not_to_sue", "strategy": "local", "section": True,
     "hint": "covenant not to sue / challenge IP validity, quote the clause or null",
     "anchors": P5_CATEGORIES["covenant_not_to_sue"]["anchors"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(?:covenant\s+not\s+to\s+sue|sue\b|sued|suing|lawsuit|contest\w*|challeng\w*|attack\w*|institut\w*\s+(?:any\s+)?(?:suit|action|proceeding)|assert\w*\s+(?:any\s+)?claims?)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no)\b|\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no)\b.{0,120}?\b(?:covenant\s+not\s+to\s+sue|sue\b|sued|suing|lawsuit|contest\w*|challeng\w*|attack\w*|institut\w*\s+(?:any\s+)?(?:suit|action|proceeding)|assert\w*\s+(?:any\s+)?claims?)\b",
     "normalize": None,
     "clean": verdict_for("covenant_not_to_sue"),
     "fallback": functools.partial(P5_find_unheaded, category="covenant_not_to_sue"),
     "retrieve": ["covenant not to sue", "shall not sue", "not contest", "not challenge", "no contests", "infringement"]},
    {"name": "non_disparagement", "strategy": "local", "section": True,
     "hint": "non-disparagement restriction, quote the clause or null",
     "anchors": P5_CATEGORIES["non_disparagement"]["anchors"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(?:disparag\w*|defam\w*|libel|slander|derogatory)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no)\b|\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no)\b.{0,120}?\b(?:disparag\w*|defam\w*|libel|slander|derogatory)\b",
     "normalize": None,
     "clean": verdict_for("non_disparagement"),
     "fallback": functools.partial(P5_find_unheaded, category="non_disparagement"),
     "retrieve": ["disparage", "defame", "derogatory", "mutual non-disparagement", "reputation"]},
    {"name": "cap_on_liability", "strategy": "local", "section": True,
     "hint": "cap or exclusion of liability, quote the clause or null",
     "anchors": P5_CATEGORIES["cap_on_liability"]["anchors"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(?:liab\w*|indemnif\w*)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no|exceed|cap|limited|maximum|uncapped|unlimited|consent)\b|\b(?:shall|will|may|must|agre\w*|covenant|never|not|without|neither|nor|no|exceed|cap|limited|maximum|uncapped|unlimited|consent)\b.{0,120}?\b(?:liab\w*|indemnif\w*)\b",
     "normalize": None,
     "clean": verdict_for("cap_on_liability"),
     "fallback": functools.partial(P5_find_unheaded, category="cap_on_liability"),
     "retrieve": ["limitation of liability", "cap on liability", "shall not exceed", "consequential damages", "in no event", "uncapped"]},
    {"name": "liquidated_damages", "strategy": "local", "section": True,
     "hint": "liquidated damages clause with fixed amount, quote the clause or null",
     "anchors": P5_CATEGORIES["liquidated_damages"]["anchors"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(?:liquidated\s+damages|as\s+liquidated|liquidated\s+amount|termination\s+payments?|termination\s+fees?|cancellation\s+fees?|payable\s+upon\s+terminat)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|pay|consent|without|neither|nor|no|equal|amount)\b|\b(?:shall|will|may|must|agre\w*|pay|consent|without|neither|nor|no|equal|amount)\b.{0,120}?\b(?:liquidated\s+damages|as\s+liquidated|liquidated\s+amount|termination\s+payments?|termination\s+fees?|cancellation\s+fees?|payable\s+upon\s+terminat)\b",
     "normalize": None,
     "clean": verdict_for("liquidated_damages"),
     "fallback": functools.partial(P5_find_unheaded, category="liquidated_damages"),
     "retrieve": ["liquidated damages", "as liquidated", "specific performance", "amount equal to", "pay as"]},
    {"name": "insurance", "strategy": "local", "section": True,
     "hint": "obligation to obtain or maintain insurance, quote the clause or null",
     "anchors": P5_CATEGORIES["insurance"]["anchors"],
     "heading": None,
     "exclude": r"(?i)\bdefinitions?\b",
     "threshold": 15.0,
     "reassemble": True,
     "member": r"(?i)\b(?:insurance\b|insured\b|insurer\b)\b.{0,120}?\b(?:shall|will|may|must|agre\w*|obtain|maintain|carry|procure|never|not|without|neither|nor|no)\b|\b(?:shall|will|may|must|agre\w*|obtain|maintain|carry|procure|never|not|without|neither|nor|no)\b.{0,120}?\b(?:insurance\b|insured\b|insurer\b)\b",
     "normalize": None,
     "clean": verdict_for("insurance"),
     "fallback": functools.partial(P5_find_unheaded, category="insurance"),
     "retrieve": ["maintain insurance", "obtain insurance", "insurance coverage", "named insured", "insurance policy"]},
]
