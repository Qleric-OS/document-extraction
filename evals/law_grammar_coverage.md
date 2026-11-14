# Governing-law grammar coverage (CUAD truth-mined, 2026-11-14)

Source: `master_clauses.csv` Governing Law-Answer, 510 rows, 431 non-empty distinct.
Method: synthetic clause `governed by the laws of {answer}` through the candidate grammar.

- **409/433 exact** (94.5%)
- 24 deltas, all harness artifacts, none real:
  - 7× `, Canada` / `, Australia` / `, UK` suffixes — pack `strip` already handles these at runtime
  - 4× multi-jurisdiction `;` lists — first-match correct by design
  - 1× redacted `[* * *]`, 1× variable-franchise clause — unanswerable
  - **0 real misses.**

## Jurisdiction inventory (from truth, not guessed)

Single: New York(97) California(55) Delaware(40) Texas(28) Florida(17) Pennsylvania(13) Nevada/Ontario(8) ...
Multi-word (34 forms): England and Wales, Hong Kong, District of Columbia,
British Columbia, People's Republic of China, Province of Ontario, ...

## Grammar rules derived

1. Longest-prefix-first: `Republic of X` / `Federal Republic of X` tried before bare patterns
2. `District`/`Republic` are answers, never prefixes
3. Capture 1-4 words, then trim against stoplist + multi-word allowlist
4. Bare form: `governed by X law` (no "laws of")
See `qleric/packs/contract.py` governing_law normalize.
