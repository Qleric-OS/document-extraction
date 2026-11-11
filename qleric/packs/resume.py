"""Resume pack: section spans are local, entities are LLM.

Sections (experience, education, skills) have stable headings across layouts,
so anchor search finds them offline. Names, titles, and skill lists need
judgment -> llm strategy.
"""
from __future__ import annotations

FIELDS = [
    {"name": "name", "strategy": "llm", "hint": "candidate full name (first non-empty line is often the name)"},
    {"name": "email", "strategy": "local", "match_first": True, "hint": "email address",
     "anchors": ["email", "e-mail", "contact", "@"],
     "normalize": r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"},
    {"name": "phone", "strategy": "local", "match_first": True, "hint": "phone number",
     "anchors": ["phone", "tel", "mobile", "cell", "contact"],
     "normalize": r"(\+?[0-9][0-9\s\-().]{6,}[0-9])"},
    {"name": "experience", "strategy": "local", "section": True, "hint": "work experience section",
     "anchors": ["experience", "work history", "employment", "work experience",
                 "professional experience", "career", "career history"],
     "member": r"\bat\b.*\(19|20[0-9]{2}.*\)"},
    {"name": "education", "strategy": "local", "section": True, "hint": "education section",
     "anchors": ["education", "qualifications", "academic", "academic background",
                 "degrees", "degree", "university", "school"],
     "member": r"\b(BSc|MSc|PhD|BA\b|MA\b|MBA|degree|university|college)\b"},
    {"name": "skills", "strategy": "llm", "hint": "skill list as comma-separated values"},
    {"name": "current_title", "strategy": "llm", "hint": "most recent job title"},
]
