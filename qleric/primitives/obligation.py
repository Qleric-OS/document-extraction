"""Obligation primitive: party + modal + action extraction with polarity and conditions.

Pure function over a section span. No LLM, no core changes. Sentence-scoped
grant logic generalizes the termination pack's tested machinery:
a sentence grants iff it names the category verb + a modal and carries
a weak/strong marker (or, for prohibitions, a negated modal), with no
disqualifier unless a strong marker protects it.
"""
from __future__ import annotations

import re

# Closed modal map. Unlisted modals never qualify.
MODALS = {
    "reserves the right to": "may",
    "shall be entitled to": "may",
    "will be entitled to": "may",
    "may be entitled to": "may",
    "is entitled to": "may",
    "is permitted to": "may",
    "may": "may",
    "can": "may",
    "agrees to": "shall",
    "agree to": "shall",
    "covenants": "shall",
    "undertakes": "shall",
    "shall": "shall",
    "must": "shall",
    "will": "shall",
}

NEGATION = (
    r"not\b|never\b|n't\b|neither\b|\bnor\b|prohibit\w*\s+(from|against)"
    r"|\brefrain\w*\s+from|\bbarred\s+from"
)

_CONDITIONS = (r"if|when|upon|unless|until|provided\s+that|in\s+the\s+event\s+(?:of|that)"
               r"|following|subject\s+to|conditioned\s+upon|contingent\s+(?:upon|on)"
               r"|except\s+(?:where|as|to\s+the\s+extent)|for\s+(?:convenience|cause|any\s+reason|no\s+reason)")

# Weak/strong markers + disqualifiers: frozen TFC-tested tables (blind-proven).
# New entries arrive only via the blind loop, never by invention.
WEAK = (r"convenience|without\s+cause|at\s+its\s+option|sole\s+discretion"
        r"|at\s+any\s+time|for\s+any\s+reason|without\s+reason"
        r"|(?:upon|on|with)\s+(?:\S+\s+){0,4}?(?:days?|months?|years?)\s+(?:prior\s+)?written\s+notice")
STRONG = (r"convenience|without\s+cause|for\s+any\s+reason|at\s+(?:its\s+)?will"
          r"|for\s+no\s+reason|without\s+reason")
DISQUALIFY = (r"effects?\s+of\s+terminat|consequences?\s+of|surviv\w*"
              r"|shall\s+not\s+relea|shall\s+not\s+relie|for\s+cause"
              r"|terminat\w+\s+(for|upon).{0,40}?(breach|default)"
              r"|breach.{0,40}?terminat|insolven|deadlock|disagre"
              r"|exercis\w*\s+\w+\s+decision|decision[\s-]making"
                      r"|competent\s+jurisdiction|exclusive\s+rights?|reserved\s+rights?"
                      r"|rights\s+granted|intellectual\s+property"
              r"|failure\s+to\s+(agree|cure|perform|pay)|cure\s+period"
              r"|shall\s+not\s+be\s+deemed|shall\s+be\s+deemed|construed\s+as"
              r"|interpreted\s+as|\bdefined\s+as|\bdefinition\s+of")

_ADVERBS = {"immediately", "promptly", "forthwith", "duly", "hereby", "thereby"}

# Per-category grant verbs (substring/regex on action+object) and section anchors.
CATEGORIES = {
    "termination": {
        "verbs": r"terminat\w*",
        "anchors": ["termination", "term and termination", "termination rights",
                    "effect of termination", "cancellation"],
        "needs_marker": True,
    },
    "non_compete": {
        "verbs": r"compet\w*|rival\w*|contend\w*|engag\w+.{0,60}?compet\w*"
                   r"|develop\w+.{0,60}?compet\w*|market\w+.{0,60}?compet\w*"
                   r"|sell\w+.{0,60}?compet\w*|carry\s+on.{0,60}?compet\w*",
        "anchors": ["non-compete", "non-competition", "covenant not to compete",
                    "restrictive covenant", "competition"],
        "needs_marker": False,
    },
    "exclusivity": {
        "verbs": r"exclusiv\w*|sole\s+(source|supplier|provider)|single\s+source",
        "anchors": ["exclusivity", "exclusive", "sole source", "single source",
                    "preferred provider"],
        "needs_marker": False,
    },
    "no_solicit_customers": {
        "verbs": r"solicit\w*|recruit\w*|poach|hire\s+away",
        "anchors": ["non-solicit", "non-solicitation", "solicit", "customers", "clients"],
        "needs_marker": False,
    },
    "no_solicit_employees": {
        "verbs": r"solicit\w*|recruit\w*|poach|hire\s+away|employ\w*\s+.*away\s+from",
        "anchors": ["non-solicit", "non-solicitation", "solicit", "employees",
                    "personnel", "hire", "recruit"],
        "needs_marker": False,
    },
    "license_grant": {
        "verbs": r"licen[sc]e|grant\w*\s+.*right|authorized\s+to\s+use",
        "anchors": ["license grant", "license", "authorized use", "grant of rights"],
        "needs_marker": False,
    },
}


def _sentences(val: str) -> list[str]:
    """Split into sentences. Mirrors local._sentences; kept local to avoid a
    primitives->local import cycle (local imports primitives.defterm)."""
    parts = re.split(r"\n+|;|(?<!\d)\.\s+", val)
    return [p.strip(" .") for p in parts if len(p.strip(" .")) > 3]


def _find_modal(sentence: str) -> tuple[str, str] | None:
    """First closed-set modal in the sentence -> (canonical, matched_text)."""
    for phrase in sorted(MODALS, key=len, reverse=True):
        m = re.search(r"\b" + phrase + r"\b", sentence, re.IGNORECASE)
        if m:
            return MODALS[phrase], m.group(0)
    return None


def _split_grant(sentence: str, modal_text: str) -> tuple[str, str] | None:
    """Split into (pre_modal, post_modal) at the modal occurrence."""
    m = re.search(r"\b" + re.escape(modal_text) + r"\b", sentence, re.IGNORECASE)
    if not m:
        return None
    return sentence[: m.start()].strip(" ,;:"), sentence[m.end():].strip(" ,;:")


def _party_from(pre: str) -> str | None:
    """Subject phrase before the modal: strip section numbers, cap length."""
    pre = re.sub(r"^[\s\d\.\)\(a-z]+\s+", "", pre).strip(" ,;:")
    pre = re.sub(r"\bagree[sd]?\s+(that|to)\b.*$", "", pre, flags=re.IGNORECASE).strip(" ,;:")
    pre = re.sub(r"^(?:that|and|or|but)\b\s*", "", pre, flags=re.I).strip(" ,;:")
    pre = re.sub(r"^(?:during|in|under|throughout)\b[^,]*,\s*", "", pre, flags=re.I).strip(" ,;:")
    if not pre or len(pre.split()) > 12:
        return None
    return pre or None


_PARTY_WORDS = ("either", "neither", "each", "both", "all", "the")


def _passive_party(post: str) -> str | None:
    """'may be terminated by X' -> X (capitalized or a known party word)."""
    m = re.search(r"\bbe\s+\w+ed\b\s+by\s+(.+?)(?:\.|,|;|$)", post)
    if not m:
        return None
    cand = m.group(1).strip(" ,;:")
    if not cand:
        return None
    cand = re.split(r"\s+(?:upon|on|within|after|before|unless|if|when|until)\b", cand, flags=re.I)[0].strip(" ,;:")
    if not cand:
        return None
    if cand[0].isupper() or cand.split()[0].lower() in _PARTY_WORDS:
        return cand
    return None


def _action_object(post: str) -> tuple[str, str | None]:
    """First verb (+adverb skip) is the action; the rest is the object.
    Passive ('be terminated by X') yields the participle; party comes from by-phrase."""
    words = post.split()
    i = 0
    while i < len(words) and words[i].lower().strip(",") in _ADVERBS | {"not", "no", "never", "n't"}:
        i += 1
    if i >= len(words):
        return post, None
    if words[i].lower() == "be" and i + 1 < len(words) and words[i + 1].lower().endswith(("ed", "en")):
        return words[i + 1], None
    verb = words[i]
    rest = " ".join(words[i + 1 :]).strip(" ,;:")
    return verb, (rest or None)


def _split_conditions(rest: str) -> tuple[str, list[str]]:
    """Split grant core from trailing condition clauses."""
    parts = re.split(r"(\b(?:" + _CONDITIONS + r")\b)", rest, flags=re.IGNORECASE)
    core = parts[0].strip(" ,;:")
    conds: list[str] = []
    i = 1
    while i < len(parts) - 1:
        conds.append((parts[i] + parts[i + 1]).strip(" ,;:."))
        i += 2
    return core, [c for c in conds if c]


def find_obligations(span: str, category: str) -> list[dict]:
    """Extract qualifying obligations for a category from a section span.

    Accept iff a sentence names the category verb + a modal and carries a
    weak/strong marker (or, for prohibitive categories, a negated modal),
    with no disqualifier unless a strong marker protects it.
    """
    cfg = CATEGORIES[category]
    needs_marker = cfg.get("needs_marker", True)
    out = []
    for sent in _sentences(span):
        if not re.search(cfg["verbs"], sent, re.IGNORECASE):
            continue
        found = _find_modal(sent)
        if not found:
            continue
        modal, modal_text = found
        split = _split_grant(sent, modal_text)
        if not split:
            continue
        pre, post = split
        marked_weak = bool(re.search(WEAK, sent, re.IGNORECASE))
        marked_strong = bool(re.search(STRONG, sent, re.IGNORECASE))
        negated = bool(re.search(NEGATION, sent, re.IGNORECASE))
        if needs_marker and not (marked_weak or marked_strong):
            continue
        if not needs_marker and not (marked_weak or marked_strong or negated):
            continue
        if re.search(DISQUALIFY, sent, re.IGNORECASE) and not marked_strong:
            continue
        core, conds = _split_conditions(post)
        action, obj = _action_object(core)
        party = _passive_party(post) or _party_from(pre)
        out.append({
            "party": party,
            "modal": modal,
            "action": action,
            "object": obj,
            "conditions": conds,
            "polarity": "neg" if negated else "pos",
            "verbatim": sent,
        })
    return out
