"""Layout circuit: hermetic red pairs for every layout slice. No CUAD, no network.

Run: python -m unittest tests.test_layout -v
Fixture rule: every shape is mined from production (corpus doc, blind miss, or
generator phrasing) and names its source. Invented shapes are not pinned.
"""
from __future__ import annotations

import unittest

from qleric.layout import sections as _sections
from qleric.layout.sections import find_section
from qleric.local import _sentences, score as _fuzzy
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


class TestSections(unittest.TestCase):
    """Mined fixtures: each names the production shape it pins.

    Every fixture runs under BOTH scorers (stdlib default + injected fuzzy).
    A split verdict is recorded per scorer — it documents sensitivity, not a bug.
    """

    def both(self, text, field, stop):
        return (find_section(text, field, stop_fields=stop),
                find_section(text, field, stop_fields=stop, scorer=_fuzzy))

    def test_headed_hit_mined(self):
        # Source: amd_001_base.pdf §7 (blind corpus headed-section shape).
        text = ("7. LIMITATION OF LIABILITY.\n"
                "In no event shall aggregate liability exceed $9,000,000.\n"
                "Questions? Call support.\n"
                "Dated March 3, 2021")
        field = {"anchors": ["limitation of liability", "liability"],
                 "heading": r"(?i)^\s*\d+\.", "threshold": 10.0}
        stop = [{"section": True, "anchors": ["governing law"]}]
        for got in self.both(text, field, stop):
            self.assertTrue(got.startswith("7. LIMITATION OF LIABILITY."))
            self.assertIn("aggregate liability exceed", got)

    def test_rival_heading_stops(self):
        # Source: contract packs' stop-anchor mechanism (termination vs law).
        text = ("12. TERMINATION\n"
                "This agreement may be terminated for convenience.\n"
                "13. GOVERNING LAW\n"
                "This agreement is governed by the laws of Texas.")
        field = {"anchors": ["termination"], "heading": r"(?i)^\s*\d+\.",
                 "threshold": 10.0}
        stop = [{"section": True, "anchors": ["governing law"]}]
        for got in self.both(text, field, stop):
            self.assertIn("terminated for convenience", got)
            self.assertNotIn("Texas", got)

    def test_member_filter_and_reassembly(self):
        # Source: renew-corpus member pattern (renew successive extend).
        text = ("1. TERM\n"
                "The initial term is one year.\n"
                "The term shall automatically renew for successive one-year periods.\n"
                "Notices go to the address above.\n"
                "2. FEES\n"
                "Pay within 30 days.\n"
                "The renewal fee is due annually.")
        field = {"anchors": ["renewal", "initial term"], "threshold": 10.0,
                 "member": r"(?i)\brenew\w*"}
        stop = [{"section": True, "anchors": ["fees"]}]
        for got in self.both(text, field, stop):
            self.assertIn("successive one-year periods", got)
            self.assertIn("renewal fee is due annually", got)
            self.assertNotIn("Notices go to", got)

    def test_reassembly_scattered_member(self):
        # Source: renewal corpus member pattern (scattered renew lines).
        text = ("NOTICE\n"
                "The Agreement is in its second renewal term.\n"
                "Please remit.\n"
                "Extended by mutual renewal agreement.\n"
                "END")
        field = {"anchors": ["renewal"], "threshold": 10.0,
                 "member": r"(?i)\brenew\w*"}
        stop = [{"section": True, "anchors": ["zzz-no-match"]}]
        for got in self.both(text, field, stop):
            self.assertIn("second renewal term", got)
            self.assertIn("mutual renewal agreement", got)
            self.assertNotIn("Please remit", got)

    def test_reassembly_duplicate_echo_mined(self):
        # Source: rnw_000_amend.pdf (amend restates the renewal sentence twice).
        # The span echoes the first member line, so it appears twice: pinned,
        # not fixed — changing it is reassembly semantics (later track).
        text = ("NOTICE\n"
                "The Agreement is in its second renewal term.\n"
                "Please remit.\n"
                "The Agreement is in its second renewal term.\n"
                "END")
        field = {"anchors": ["renewal"], "threshold": 10.0,
                 "member": r"(?i)\brenew\w*"}
        stop = [{"section": True, "anchors": ["zzz-no-match"]}]
        for got in self.both(text, field, stop):
            self.assertEqual(got.count("second renewal term"), 2)
            self.assertNotIn("Please remit", got)

    def test_decoy_exclusion(self):
        # Source: incorporation-decoy exclusion (law packs' demote family).
        text = ("1. INCORPORATION\n"
                "The company was incorporated under the laws of Delaware.\n"
                "2. GOVERNING LAW\n"
                "This agreement is governed by the laws of Texas.")
        field = {"anchors": ["governing law"], "heading": r"(?i)^\s*\d+\.",
                 "exclude": r"(?i)incorporat", "threshold": 10.0}
        stop = [{"section": True, "anchors": ["zzz-no-match"]}]
        for got in self.both(text, field, stop):
            self.assertIn("laws of Texas", got)
            self.assertNotIn("Delaware", got)

    def test_grant_gated_skip(self):
        # Source: TFC verdict gating (P5 weak/strong + disqualify).
        grant = ("12. TERMINATION\n"
                 "This agreement may be terminated for convenience upon 30 days written notice.\n"
                 "13. GOVERNING LAW\n"
                 "This agreement is governed by the laws of Texas.")
        effects = ("12. TERMINATION\n"
                   "The effects of termination shall survive closing.\n"
                   "13. GOVERNING LAW\n"
                   "This agreement is governed by the laws of Texas.")
        field = {"anchors": ["termination"], "heading": r"(?i)^\s*\d+\.",
                 "threshold": 10.0,
                 "qualify": r"(?i)convenience|without cause",
                 "qualify_strong": r"(?i)convenience|without cause",
                 "disqualify": r"(?i)surviv|consequences"}
        stop = [{"section": True, "anchors": ["governing law"]}]
        for got in self.both(grant, field, stop):
            self.assertIn("for convenience", got)
        for got in self.both(effects, field, stop):
            self.assertIsNone(got)

    def test_stop_required(self):
        with self.assertRaises(ValueError):
            find_section("12. TERMINATION\nBody here.", {"anchors": ["termination"]})

    def test_canonical_home(self):
        self.assertIs(find_section, _sections.find_section)


if __name__ == "__main__":
    unittest.main()
