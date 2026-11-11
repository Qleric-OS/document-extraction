"""Your-docs validation: same pattern we use internally, on your own files.

1. Drop private PDFs into samples/real/ (gitignored, never committed).
2. Add hand-checked truth rows below (exact strings from the docs).
3. Run: python3 evals/eval.py samples/corpus/corpus.jsonl  # synthetic first
   then: python3 -m evals.validate_real  # your docs against your truth

Every miss is either a new anchor/member pattern (fix the pack) or a new
mess axis (extend evals/generate.py so the corpus covers it next time).
That loop is the product: your docs make the shared machinery smarter
without your docs ever leaving your machine.
"""
from __future__ import annotations

# Copy this row per doc. pack must exist in qleric.packs.
# expected: exact strings (email/phone/dates) or body substrings (sections).
EXAMPLE = {
    "id": "my_cv",
    "pack": "resume",
    "pdf": "samples/real/my_cv.pdf",
    "expected": {
        "name": "Exact Name As Printed",
        "email": "name@example.com",
        "phone": "+1 555-000-0000",
        "current_title": "Most Recent Title",
        "_bodies": {"experience": ["One distinctive job line"]},
    },
}

REAL: list[dict] = [
    # EXAMPLE,
]
