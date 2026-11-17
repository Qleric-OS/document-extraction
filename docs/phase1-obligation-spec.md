# Phase 1: Obligation Primitive + Cross-Category Blind

Status: SPEC (not yet built). Scaffolding only — no query-surface changes, no field wiring.
Phase 2 migrates fields onto it, one per commit, each gated on an unchanged blind.

## 1. Deliverable (explicitly bounded)

- `qleric/primitives/obligation.py`: one pure function + pattern tables.
- `evals/validate_obligation_blind.py`: stratified blind harness (new file, reuses
  `load_doc`/`ungradeable`/exclusions from `validate_field_blind.py` — no duplication).
- A step-0 baseline number. No field wiring, no core changes, no new LLM calls.

Out of scope: cross-references ("subject to Section 5.2"), amendments/restatements,
multi-value assembly, defined-term resolution beyond verbatim subjects (that's P6),
any new disqualify/qualify semantics beyond what's listed here.

## 2. Output schema

```python
{
  "party": str | None,      # verbatim subject phrase; unresolved ("the Company" stays as-is)
  "modal": str,             # normalized, closed set below
  "action": str,            # verbatim main verb phrase (no decomposition)
  "object": str | None,     # verbatim object/complement, or null
  "conditions": list[str],  # verbatim condition clauses, possibly empty
  "polarity": "pos" | "neg",
  "verbatim": str,          # full granting sentence
  "grounded": bool,
  "page_number": int | None,
}
```

Modal map (closed; unlisted modals never qualify):
`may, can, is entitled to, is permitted to, reserves the right to` → `may`
`shall, must, will, agrees to, agree to, covenants, undertakes` → `shall`

Polarity is separate from modal. Negative iff the sentence contains:
`not | never | n't | neither | nor | prohibited from | refrain(s)? from | is barred from`
attached to the grant verb. `except | unless | until` do NOT flip polarity —
they go to `conditions` (e.g. "may not X except Y" = neg + condition Y).

`action` is the whole verb phrase, matched by substring/regex at the category layer — no decomposition. `conditions` splits on:
`if | when | upon | unless | until | provided that | in the event (of|that) |
following | subject to | conditioned upon | contingent (upon|on) | except (where|as|to the extent)`.

Worked examples:

- "Either Party may terminate this Agreement for convenience upon 30 days written notice."
  → party=`Either Party`, modal=`may`, action=`terminate`, object=`this Agreement`,
  conditions=[`for convenience`, `upon 30 days written notice`], polarity=pos.
  (Whether "for convenience" *counts* is the category layer's decision, not P5's.)
- "During the Term, Employee shall not engage in any business that competes with the Company."
  → party=`Employee`, modal=`shall`, action=`engage in any business that competes with the Company`,
  polarity=neg. Category match runs regexes over action+object (`compet\w*` → non-compete).
- "SFJ may terminate this Agreement ... in the event PB exercises its decision-making authority."
  → conditions=[`in the event PB exercises its decision-making authority`]; the
  decision-gate disqualifier fires on the condition → sentence excluded. This is
  exactly the TFC Phasebio case, generalized.

## 3. Admission rule (the R2 lesson, encoded)

Headed sections only, via the existing `find_section` machinery with a P5 union
anchor set (`covenant`, `agree`, `restrict`, `exclusive`, `solicit`, `compete`,
`terminate`, plus the per-category nouns below). Threshold unchanged (55).
**Unheaded grants are explicitly out**: R2 proved line-grant candidacy and the
doc-wide fallback both trade FP for TP at a loss. No weak-only unheaded starts,
no fallback pass. A grant the section machinery can't seat is a miss, honestly reported.

## 4. Starter pattern inventory (seed, then blind-driven only)

- **Modals**: §2 closed set. Additions require a blind miss + a non-ambiguous reading.
- **Grant verbs by category** (substring/regex on action+object, case-insensitive):
  - termination: `terminat\w*`
  - non-compete: `compet\w*|rival|contend`
  - exclusivity: `exclusiv\w*|sole\s+(source|supplier|provider)|single\s+source`
  - no-solicit: `solicit\w*|recruit\w*|poach|hire\s+away|employ\s+.*away\s+from`
  - license-grant (diagnostic only in Phase 1): `licen[sc]e|grant.*right|authorized\s+to\s+use`
- **Disqualifiers** (sentence-scoped, inherited verbatim from the TFC set that
  survived blind measurement — no new ones invented here):
  effects/consequences (`effects?\s+of\s+terminat|consequences?\s+of|surviv\w*|
  shall\s+not\s+relea|shall\s+not\s+relie`), cause/breach/default/insolvency,
  conditional gates (`deadlock|disagre|exercis\w*\s+\w+\s+decision|
  decision[\s-]making`), failure-to-*, cure periods.
- **Weak markers** (grant candidacy; disqualify still applies): convenience,
  without cause, at its option, sole discretion, at any time, for any reason,
  without reason, bare notice-with-verb.
- **Strong markers** (protect against disqualify): convenience, without cause,
  for any reason, at will, for no reason, without reason.
- New patterns enter ONLY via the loop in §6 (miss → shape → pattern → full-blind proof).

## 5. Blind protocol (`validate_obligation_blind.py`)

- **Sampling**: stratified, 25 docs per category × 4 categories
  (non-compete, exclusivity, no-solicit-customers, no-solicit-employees),
  seed 7, same exclusions as the field blinds (rows[:12] + debugged prefixes).
  Termination reuses TFC's 71/96 — not re-sampled, not re-graded.
- **Grading**: (a) presence — a category counts Yes iff ≥1 qualifying obligation
  for it is found; hit iff found == truth. (b) diagnostic, manual n=20 spot-check:
  party/action correct on found obligations (reported, not gated).
- **Majority bars** (master_clauses.csv, n=510):

  | category | Yes | majority-No |
  |---|---|---|
  | non-compete | 119 (23.3%) | 76.7% |
  | exclusivity | 180 (35.3%) | 64.7% |
  | no-solicit customers | 34 (6.7%) | 93.3% |
  | no-solicit employees | 59 (11.6%) | 88.4% |
  | termination (TFC blind, reused) | 183 (35.9%) | 64.1% |

- **Acceptance, per category**: recall on sampled Yes docs ≥ 50% AND false
  positives ≤ 3 per 25 sampled. (Deliberately not "beat majority by N": at 93%
  majority that bar is either impossible or rewards null-guessing. TP/FP counts
  are the honest metric under imbalance.)
- **Step 0 is the baseline**: build harness, run, record. Every later change is
  judged by miss-identity diff, not just totals (the R2 lesson).

## 6. Iteration loop (the only way patterns get in)

miss → name the exact shape (quote the sentence) → propose the narrowest
pattern/disqualifier → full 100-doc blind → commit iff TP-identical-or-better
AND FP-identical-or-better. Net-zero churn (equal TP/FP swaps) is a revert, not
a commit — the renewal as-follows episode is the standing example.

## 7. Known limitations (carried, not fixed here)

- Multi-value obligations ("5 years; 2 years", dual grants) → first verified
  value wins; documented, not silently passed.
- Verbatim truths with annotator typos stay misses (never touch the grader).
- Unheaded grants stay misses (admission rule §3).
- Ambiguous deal-specific rights (banks, Phasebio-class) go to manual/big-model
  review with reasons — the big-tier probe pattern, not grammar.
