"""Real-doc validation truth (hand-checked). Format matches corpus.jsonl rows.

Resume truth: exact strings from doc text (verify with fitz extraction).
Contract probes (NDA/DPA): pack=contract probe fields, graded on presence of
key clauses, not exact values — these docs define the contract pack later.
"""
REAL = [
    {"id": "real_cv1", "pack": "resume", "pdf": "samples/real/Mohamed-cv.pdf",
     "expected": {
         "name": "MOHAMED ABDULKARIM MOHAMED",
         "email": "Mohamed.m365@outlook.com",
         "phone": "+44 7956 765580",
         "current_title": "Founder & Lead Developer",
         "_bodies": {"experience": ["AI Contract Analysis Platform (June 2025-Present)"]},
     }},
    {"id": "real_cv2", "pack": "resume", "pdf": "samples/real/Mohamed-cv-IT.pdf",
     "expected": {
         "name": "Mohamed Abdulkarim Mohamed",
         "email": "Mohamed.m365@outlook.com",
         "phone": "+44 7956 765580",
         "current_title": "Telecommunications Engineer",
         "_bodies": {"experience": ["Telecommunications Engineer | Circet"]},
     }},
]
