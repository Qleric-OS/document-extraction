# Evals: 90-case synthetic messy corpus with exact ground truth

Regenerate: `python3 evals/generate.py` (seeded `20261111`, deterministic).
Run keyless: `python3 evals/eval.py samples/corpus/corpus.jsonl`
Run with LLM: `OPENAI_API_KEY=... MODEL=gpt-6-luna python3 evals/eval.py samples/corpus/corpus.jsonl --deep`

## Stratification (30 per pack)

**Invoice** (`inv_000-029`): label variants (INV/Ref/Bill No), US/EU/ISO dates,
4 currency formats, upper/lowercase, junk lines, 20% missing due_date, 25%
missing tax, 15% two-page, buyer/seller company rotation.
**Resume** (`res_000-029`): section-heading variants (Experience/Work History/
Career, Education/Qualifications/Degrees), 70% skills section, order swaps,
case noise, junk injection, shuffled lines (10%).
**PII** (`pii_000-029`): 1-3 emails, always phone, 80% SSN, 70% card, 60% IBAN,
order-id decoy (must NOT match card), 30% two-page.

## Metrics

- **acc** value match (money digits-only, dates parsed, PII set-match, sections body-line recall)
- **grd** grounded hits / hits (verbatim + bbox attached)
- **fg** false grounds (grounded but verbatim absent from source) — must stay 0
- null-truth and correctly-absent fields are skipped, not graded
