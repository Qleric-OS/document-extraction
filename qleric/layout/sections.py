"""Section discovery: heading + contiguous body, member reassembly. No packs import."""
from __future__ import annotations

import re

from .sentences import _sentences
from .types import SECTION_DEFAULTS


def _exact_score(span: str, anchors: list[str]) -> float:
    """Stdlib word-overlap scorer (isolated default, mirrors local's no-fuzz path).

    Production injects the fuzzy scorer explicitly. NOTE: this skips the
    label-stripping that `local.score` applies — the default is for
    portability, not parity. Isolated tests run both and record any split.
    """
    words = set(span.lower().split())
    return max((len(set(a.lower().split()) & words) / max(len(a.split()), 1)
                for a in anchors), default=0.0) * 100


def _has_grant(val: str, qualify, strong, disqualify) -> bool:
    """A granting sentence names termination + a convenience marker, no disqualifier.

    Sentence scope stops tail boilerplate ("termination for any reason shall
    not release...") from masquerading as a grant, and stops effects-adjacent
    text from poisoning a real grant elsewhere in the section.
    """
    for s in _sentences(val):
        if not re.search(r"terminat\w*", s, re.IGNORECASE):
            continue
        marked = (strong and re.search(strong, s, re.IGNORECASE)) or (
            qualify and re.search(qualify, s, re.IGNORECASE))
        if not marked:
            continue
        if disqualify and re.search(disqualify, s, re.IGNORECASE):
            continue
        return True
    return False


def find_section(text: str, field: dict, stop_anchors: list[str] | None = None,
                 stop_fields: list[dict] | None = None, scorer=None) -> str | None:
    """Section body: heading + contiguous lines until a rival heading,
    plus doc-wide reassembly of member-pattern lines (shuffle-proof).

    Reads from the field dict: anchors, threshold, member, heading, exclude,
    qualify, qualify_strong, disqualify, reassemble. Only stop anchors stay
    external (they depend on sibling fields, not this one). `scorer` is
    injected (production passes the fuzzy one); the stdlib default keeps the
    package dependency-closed.
    """
    if scorer is None:
        scorer = _exact_score
    anchors = field.get("anchors", [])
    threshold = field.get("threshold", SECTION_DEFAULTS["span_threshold"])
    member = field.get("member")
    heading = field.get("heading")
    exclude = field.get("exclude")
    qualify = field.get("qualify")
    strong = field.get("qualify_strong")
    disqualify = field.get("disqualify")
    reassemble = field.get("reassemble", True)
    if stop_anchors is None:
        if stop_fields is None:
            raise ValueError("sections need stop_fields or stop_anchors (no pack default)")
        stop_anchors = [a for f in stop_fields if f.get("section")
                        for a in f.get("anchors", [])]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    starts: list[tuple[int, str]] = [(i, ln) for i, ln in enumerate(lines)]
    for i, ln in enumerate(lines):  # paragraph-embedded clauses: clause windows can start
        if len(ln) > SECTION_DEFAULTS["long_line"]:
            for part in re.split(r";|\(|\)|, the |, and |(?<!\d)\. ", ln):
                part = part.strip()
                if len(part) > SECTION_DEFAULTS["min_window"]:
                    starts.append((i, part))  # origin line index preserves doc order
    cands: list[tuple[tuple[int, float], int, str]] = []
    for pos, (origin, ln) in enumerate(starts):
        if exclude and re.search(exclude, ln, re.IGNORECASE):
            continue  # false friend: never a section start
        if heading and not re.search(heading, ln, re.IGNORECASE):
            continue  # unheaded span: not a section start (body handled by member)
        s = scorer(ln, anchors)
        if s <= threshold:
            continue
        density = 0
        if member:
            own = [t for o, t in starts[pos:pos + 4] if o == origin]
            density = len(re.findall(member, " ".join(own), re.IGNORECASE))
        cands.append(((density, s), origin, ln))
    cands.sort(reverse=True)  # densest, highest-scoring first
    for _, origin, span in cands:
        body = []
        best_pos = next((p for p, (o, t) in enumerate(starts) if o == origin and t == span), -1)
        for o2, t2 in starts[best_pos + 1:]:
            if o2 != origin:
                break
            body.append(t2)
        for i, ln in enumerate(lines):
            if i <= origin:
                continue  # heading line itself; body follows (or window covers it)
            if scorer(ln, stop_anchors) > SECTION_DEFAULTS["stop_threshold"] and scorer(ln, anchors) <= scorer(ln, stop_anchors):
                break  # a different section starts
            body.append(ln)
        if member:
            # filter contiguous body to member lines (keeps section identity)
            body = [ln for ln in body if re.search(member, ln, re.IGNORECASE)]
            if reassemble:  # shuffled docs: pull scattered members doc-wide
                seen = set(body)
                for ln in lines:
                    if ln not in seen and re.search(member, ln, re.IGNORECASE):
                        body.append(ln)
                        seen.add(ln)
                order = {ln: i for i, ln in enumerate(lines)}
                body.sort(key=lambda ln: order.get(ln, 0))
        val = "\n".join([span, *body]) if body else span
        if disqualify and not _has_grant(val, qualify, strong, disqualify):
            continue  # no granting sentence: conditional/cause/effects only
        if not disqualify and qualify and not re.search(qualify, val, re.IGNORECASE):
            continue  # right shape, wrong substance: try next heading
        return val
    return None
