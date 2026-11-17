# Phase 1 record: obligation primitive + cross-category blind

Status: BUILT and blind-validated (commit `307189a`). This document describes
what shipped, not what is planned. The pre-build plan was deliberately *not*
kept in the repo; this record replaces it.

## What shipped

- `qleric/primitives/obligation.py` — pure function `find_obligations(span, category)`.
- `evals/validate_obligation_blind.py` — stratified blind, 25 docs × 4 categories,
  deterministic seed, reuses sampling/loading from `validate_field_blind.py`.
- No core changes. No new LLM calls. Two new files, zero modifications elsewhere.

## Schema (as built)

```python
{
  "party": str | None,   # verbatim subject; unresolved ("the Company" stays as-is)
  "modal": str,           # normalized to a closed set (below)
  "action": str,          # first verb after the modal (adverbs/negation skipped)
  "object": str | None,   # remainder of the clause, or None
  "conditions": list[str],# verbatim condition clauses, possibly empty
  "polarity": "pos" | "neg",
  "verbatim": str,        # granting sentence
}
```
Grounding is applied by the caller via `grounding.locate`, not inside the primitive.

Modal map (closed; unlisted modals never qualify):
`reserves the right to`, `is|shall|will|may be entitled to`, `is permitted to`,
`may`, `can` → `may`;
`agrees to`, `agree to`, `covenants`, `undertakes`, `shall`, `must`, `will` → `shall`.

Polarity is separate from the modal. Negative iff the sentence contains:
`not | never | n't | neither | nor | prohibit\w* (from|against) | refrain\w* from | barred from`.
`except | unless | until` do NOT flip polarity — they split into `conditions`.

Conditions split on: `if | when | upon | unless | until | provided that |
in the event (of|that) | following | subject to | conditioned upon |
contingent (upon|on) | except (where|as|to the extent) | for (convenience|cause|any reason|no reason)`.

Party cleanup, in order: strip section numbers; strip trailing `agree(d|s)? (that|to) ...`;
strip leading conjunctions (`that|and|or|but`); strip leading durational PP
(`during|in|under|throughout ... ,`); drop if empty or >12 words.
Passive: `be <verb>ed by X` → action is the participle, party comes from the
by-phrase (capitalized, or a party word: either|neither|each|both|all|the),
truncated at the next condition introducer.

## Admission rule (as built)

Headed sections via the existing `find_section`, with a per-category anchor set
and `reassemble=False`. Unheaded fallback exists but is fenced: a doc-wide
sentence is accepted ONLY with a negated modal or a strong marker.
Weak-only unheaded matches stay excluded — the TFC line-grant experiment proved
they FP at scale. (This differs from the pre-build plan, which had no fallback;
the fence is what makes it safe.)

## Pattern inventory (as built, blind-proven)

Grant verbs per category (substring/regex on action+object, case-insensitive):
- termination: `terminat\w*`
- non-compete: `compet\w*|rival\w*|contend\w*` plus engage/develop/market/sell/carry-on
  within 60 chars of a `compet\w*` object (canonical non-compete phrasing is
  "shall not engage in any Competitive Business", not "shall not compete")
- exclusivity: `exclusiv\w*|sole\s+(source|supplier|provider|distributor)|single\s+source`
- no-solicit: `solicit\w*|recruit\w*|poach|hire\s+away|employ\s+.*away\s+from`
- license-grant (diagnostic only, unblinded): `licen[sc]e|grant.*right|authorized\s+to\s+use`

Disqualifiers (sentence-scoped; a strong marker protects):
`effects?\s+of\s+terminat|consequences?\s+of|surviv\w*|shall\s+not\s+relea|
shall\s+not\s+relie|for\s+cause|terminat\w+\s+(for|upon).{0,40}?(breach|default)|
breach.{0,40}?terminat|insolven|deadlock|disagre|exercis\w*\s+\w+\s+decision|
decision[\s-]making|failure\s+to\s+(agree|cure|perform|pay)|cure\s+period|
competent\s+jurisdiction|exclusive\s+rights?|reserved\s+rights?|
rights\s+granted|intellectual\s+property`

Weak markers (grant candidacy, disqualify applies): convenience, without cause,
at its option, sole discretion, at any time, for any reason, without reason,
bare notice-with-written-notice.
Strong markers (protect against disqualify): convenience, without cause,
for any reason, at will, for no reason, without reason.

New entries arrive ONLY via: miss → name the exact sentence → narrowest pattern →
full 100-doc blind → commit iff TP-identical-or-better AND FP-identical-or-better.
Net-zero churn is a revert. (Precedents: the `as follows` and MAE/CoC reversals,
and the line-grant/fallback reversals that motivated the fence above.)

## Blind results (the acceptance record)

Stratified 25 docs × 4 categories, seed 7, same exclusions as the field blinds.
Acceptance was: recall ≥ 50% of sampled Yes AND FP ≤ 3 per 25.

| category | TP | FP | TN | FN | recall | verdict |
|---|---|---|---|---|---|---|
| non_compete | 10 | 2 | 11 | 2 | 0.83 | PASS |
| exclusivity | 8 | 3 | 10 | 4 | 0.67 | PASS |
| no_solicit_customers | 6 | 1 | 12 | 5 | 0.55 | PASS |
| no_solicit_employees | 9 | 0 | 13 | 3 | 0.75 | PASS |
| TOTAL | 33 | 6 | 46 | 14 | — | 79/99 |

Termination reuses the TFC field blind (71/96 keyless) — not re-sampled.

## Known limitations (carried, not fixed here)

- Multi-value obligations → first verified value wins; documented, not silently passed.
- Annotator-typo'd and canonicalized truths stay misses; the grader is never touched.
- Unheaded weak-only grants stay excluded by design.
- Ambiguous deal-specific rights go to manual/big-model review with reasons.
- Cross-references ("subject to Section 5.2"), amendments/restatements, and
  defined-term resolution beyond verbatim subjects are explicitly out (P6 and later).
