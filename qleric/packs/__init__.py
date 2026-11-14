"""Domain packs: narrow schemas on top of the grounded core.

Field spec — every key a pack field may declare:

| key | applies to | what it does |
|---|---|---|
| name | all | field id in output |
| strategy | all | local, table, pii, or llm |
| hint | llm/local | human description; also the default retrieval keywords |
| anchors | local | fuzzy-match phrases for span search |
| normalize | local | regex cleaning the span (capture group = value); None = span is the value |
| strip | local | trailing words to strip after normalize |
| reject | local | value-shape trap to skip (e.g. year ranges matching phone) |
| match_first | local | accept direct pattern hit without anchor (self-identifying: email/phone) |
| value_first | local | distinctive pattern admits the span; anchors rank (e.g. jurisdictions) |
| section | local | treat as headed section (find_section, not find_span) |
| heading | section | regex a line must match to start the section |
| exclude | section | false-friend lines that never start the section |
| member | section | body-line pattern (reassembly + filtering) |
| qualify | section | assembled value must match, else None (wrong-substance guard) |
| stop_fields | section | rival-heading pack (defaults to own pack's sections) |
| reassemble | section | doc-wide member sweep for shuffled docs (default True) |
| columns | table | header synonyms for row-grounded items |
| pattern | pii | sweep regex; all occurrences returned |
| retrieve | llm | keywords for targeted context windows (default: hint words) |
| escalate | llm | run MODEL_BIG when small misses or ungrounds |
| headings | any | +50 score bonus when present in span (strongest signal) |

Source enum in output: local, table, pii, llm-small, llm-big.
"""
from .contract import FIELDS as CONTRACT_FIELDS
from .invoice import FIELDS as INVOICE_FIELDS
from .pii import FIELDS as PII_FIELDS
from .resume import FIELDS as RESUME_FIELDS

__all__ = ["CONTRACT_FIELDS", "INVOICE_FIELDS", "PII_FIELDS", "RESUME_FIELDS"]
