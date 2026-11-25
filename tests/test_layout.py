"""Layout L1 circuit: one sentence splitter. Pins behavior, no CUAD needed."""
from __future__ import annotations

import unittest

from qleric.local import _sentences
from qleric.primitives import obligation as O


class TestSplitter(unittest.TestCase):
    def test_single_source(self):
        self.assertIs(O._sentences, _sentences)

    def test_numeric_periods(self):
        # Guard is digit-before only: "Sec." splits, "5.2" doesn't.
        self.assertEqual(_sentences("See Sec. 5.2 for details. It applies."),
                         ["See Sec", "5.2 for details", "It applies"])
        self.assertEqual(_sentences("version v1.27 is out. Upgrade now."),
                         ["version v1.27 is out", "Upgrade now"])
        self.assertEqual(_sentences("cap is $86M. No penalty."),
                         ["cap is $86M", "No penalty"])

    def test_abbreviations_pinned(self):
        # "U.S." survives (no whitespace inside); "law" drops as ≤3 chars.
        # Pre-existing quirks, pinned not fixed.
        self.assertEqual(_sentences("governed by U.S. law. Next clause."),
                         ["governed by U.S", "Next clause"])

    def test_semicolons_isolate_grants(self):
        self.assertEqual(_sentences("may terminate for convenience; no penalty. Done."),
                         ["may terminate for convenience", "no penalty", "Done"])

    def test_parens_kept(self):
        self.assertEqual(_sentences("term (the Initial Term) is five years. Renewals follow."),
                         ["term (the Initial Term) is five years", "Renewals follow"])

    def test_cjk_noop(self):
        s = "快速的棕色狐狸跳过懒狗" * 4
        self.assertEqual(_sentences(s), [s])

    def test_short_fragments_dropped(self):
        self.assertEqual(_sentences("a. I am here. Ok."),
                         ["I am here"])
        self.assertEqual(_sentences(""), [])

    def test_multiline(self):
        self.assertEqual(_sentences("line one\nline two"), ["line one", "line two"])


if __name__ == "__main__":
    unittest.main()
