# Evals: 90-case synthetic messy corpus with exact ground truth

Regenerate: `python3 evals/generate.py` (seeded `20261111`, deterministic).
Run keyless: `python3 evals/eval.py samples/corpus/corpus.jsonl`
Run with LLM: `OPENAI_API_KEY=... MODEL=gpt-6-luna python3 evals/eval.py samples/corpus/corpus.jsonl --deep`

## Stratification (30 per pack)

**Invoice** (`inv_000-029`): label variants (INV/Ref/Bill No), US/EU/ISO dates,
4 currency formats, upper/lowercase, junk lines, 20% missing due_date, 25%
missing tax, 15% two-page, buyer/seller company rotation, filing-header
decoys (dates that must NOT match), paragraph-embedded values.

- null-truth and correctly-absent fields are skipped, not graded

## Retrieval workbench

`retrieve` keywords decide what the model sees. Tune them visually:

```bash
python3 evals/retrieve.py <doc> <pack> <field>   # ranked windows + stats
```

Every response carries `meta.retrieval`: windows hit/sent per field, chars,
fallback flag. CUAD clause truth mixes Yes/No flags (absent = null correct,
cite = hallucination) and free text (expect grounded cite).
