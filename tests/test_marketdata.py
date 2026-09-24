"""cross_check is a CLAUDE.md rule with no test.

  "Never trade on a single unverified price. Every stop and every size is
   computed from it. cross_check() compares the broker's price against an
   independent one; if they disagree by more than 50bps, STAND DOWN on that
   symbol — do not average the two or pick a winner."

It is the last line between a bad tick and a real order, and until now nothing
pinned the threshold, the direction of the comparison, or the wording a session
acts on.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import marketdata
from engine.market import Bar
import datetime as dt


def _bars(close):
    return [Bar(dt.date(2026, 9, 24), close, close, close, close, 1e6)]


class TestCrossCheckStandsDownOnDisagreement(unittest.TestCase):

    def _check(self, broker_px, ref_px, tol=50.0):
        with mock.patch.object(marketdata, "daily_bars",
                               lambda s, rng="5d": _bars(ref_px)):
            return marketdata.cross_check("DT", broker_px, tolerance_bps=tol)

    def test_identical_prices_agree(self):
        r = self._check(58.47, 58.47)
        self.assertTrue(r["agree"])
        self.assertEqual(r["diff_bps"], 0.0)

    def test_just_inside_the_tolerance_agrees(self):
        # 49bps on a $100 reference.
        r = self._check(100.49, 100.0)
        self.assertTrue(r["agree"])

    def test_just_outside_the_tolerance_stands_down(self):
        r = self._check(100.51, 100.0)
        self.assertFalse(r["agree"])
        self.assertIn("DISAGREE", r["note"])
        self.assertIn("do not trade", r["note"])

    def test_exactly_at_the_tolerance_agrees(self):
        # The boundary is documented as "more than 50bps" — 50 itself passes.
        r = self._check(100.50, 100.0)
        self.assertEqual(r["diff_bps"], 50.0)
        self.assertTrue(r["agree"])

    def test_the_comparison_is_symmetric(self):
        # A broker price BELOW the reference must stand down just the same; an
        # absolute difference, not a signed one.
        low = self._check(99.0, 100.0)
        high = self._check(101.0, 100.0)
        self.assertFalse(low["agree"])
        self.assertFalse(high["agree"])
        self.assertAlmostEqual(low["diff_bps"], high["diff_bps"], places=0)

    def test_the_note_names_the_symbol_so_a_refusal_is_actionable(self):
        self.assertIn("DT", self._check(110.0, 100.0)["note"])

    def test_both_prices_are_returned_so_neither_is_averaged(self):
        # The rule forbids splitting the difference. Both must survive into
        # the result for the refusal to be checkable afterwards.
        r = self._check(110.0, 100.0)
        self.assertEqual(r["broker"], 110.0)
        self.assertEqual(r["reference"], 100.0)

    def test_the_RKLB_case_that_M30_found_would_have_been_caught(self):
        # IEX said the 20-day high was 70.56 where the consolidated tape said
        # 71.21 — 91bps, comfortably past the 50bps stand-down.
        r = self._check(70.56, 71.21)
        self.assertFalse(r["agree"])
        self.assertGreater(r["diff_bps"], 50.0)
