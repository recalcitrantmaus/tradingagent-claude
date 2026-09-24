"""engine/feasibility.py is the arithmetic behind docs/01 — the document
CLAUDE.md says to read "before forming any view on what this can achieve" —
and it had no tests.

These pin the claims the mandate rests on, so that if the maths is ever changed
in a way that makes the target look reachable, the change is visible rather
than persuasive.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.feasibility import KellySim, compounded, edge_sensitivity, \
    target_reality_check


class TestTheTargetCompoundsAbsurdly(unittest.TestCase):

    def test_five_percent_a_week_annualises_past_1000_percent(self):
        # docs/01 and the README both quote +1,164%.
        self.assertAlmostEqual(target_reality_check()["annualized"], 11.64,
                               delta=0.05)

    def test_300_dollars_becomes_about_3800_in_a_year(self):
        """Stated so the absurdity is in a test rather than only in prose.

        The exact figure matters: 300 x 1.05^52 = 3792.84, a 12.6x. An earlier
        draft of this test asserted "six figures" from memory and failed —
        +1,164% annualised on $300 is not $100k, and a test written from
        recollection rather than from the arithmetic is how a wrong number
        gets into a document that other decisions cite.
        """
        self.assertAlmostEqual(target_reality_check()["after_52_weeks"],
                               3792.84, delta=0.5)
        self.assertGreater(target_reality_check()["after_3_years"], 500_000)

    def test_compounding_is_monotonic_in_rate_and_in_weeks(self):
        self.assertGreater(compounded(0.05, 52, 300), compounded(0.04, 52, 300))
        self.assertGreater(compounded(0.05, 52, 300), compounded(0.05, 26, 300))

    def test_a_zero_rate_does_not_compound(self):
        self.assertAlmostEqual(compounded(0.0, 52, 300.0), 300.0)


class TestEdgeIsTheOnlyThingThatMatters(unittest.TestCase):

    def test_no_edge_means_no_amount_of_sizing_reaches_the_target(self):
        # The central claim of docs/01, and the reason the 5% figure is a
        # hurdle rather than a quota: a coin flip at 1:1 cannot be sized into
        # a positive expectation.
        flat = KellySim(win_rate=0.50, win_multiple=1.0, loss_multiple=1.0,
                        trades_per_week=5)
        self.assertAlmostEqual(flat.edge_per_trade_R(), 0.0)
        self.assertEqual(flat.risk_needed_for(0.05), float("inf"))

    def test_a_negative_edge_is_also_infinite(self):
        bad = KellySim(0.35, 1.0, 1.0, 5)
        self.assertLess(bad.edge_per_trade_R(), 0)
        self.assertEqual(bad.risk_needed_for(0.05), float("inf"))

    def test_a_real_edge_gives_a_finite_but_large_required_risk(self):
        good = KellySim(0.45, 2.0, 1.0, 5)
        need = good.risk_needed_for(0.05)
        self.assertLess(need, float("inf"))
        self.assertGreater(need, DEFAULT.max_risk_per_trade_pct,
                           "5%/week must demand more risk than the 2% cap "
                           "allows, or the cap would not be the binding rule")

    def test_kelly_is_zero_without_an_edge_and_never_negative(self):
        self.assertEqual(KellySim(0.30, 1.0, 1.0, 5).kelly_fraction(), 0.0)
        self.assertEqual(KellySim(0.50, 1.0, 1.0, 5).kelly_fraction(), 0.0)
        self.assertGreater(KellySim(0.55, 2.0, 1.0, 5).kelly_fraction(), 0.0)

    def test_edge_per_trade_is_the_textbook_expression(self):
        k = KellySim(0.40, 2.0, 1.0, 5)
        self.assertAlmostEqual(k.edge_per_trade_R(), 0.40 * 2.0 - 0.60 * 1.0)


class TestTheMonteCarloBehavesLikeReality(unittest.TestCase):

    def test_it_is_reproducible_for_a_fixed_seed(self):
        k = KellySim(0.45, 2.0, 1.0, 5)
        self.assertEqual(k.monte_carlo(0.02, 52, trials=200, seed=3),
                         k.monte_carlo(0.02, 52, trials=200, seed=3))

    def test_sizing_up_without_an_edge_buys_ruin_not_return(self):
        # docs/04's most repeated finding, pinned as arithmetic.
        flat = KellySim(0.50, 1.0, 1.0, 5)
        small = flat.monte_carlo(0.02, 52, trials=400, seed=11)
        large = flat.monte_carlo(0.25, 52, trials=400, seed=11)
        self.assertGreater(large["prob_lose_half_or_more"],
                           small["prob_lose_half_or_more"])
        self.assertLess(large["median_final_multiple"],
                        small["median_final_multiple"],
                        "sizing up at zero edge must not improve the median")

    def test_more_edge_produces_a_better_median(self):
        weak = KellySim(0.42, 1.5, 1.0, 5).monte_carlo(0.02, 52, trials=400, seed=13)
        strong = KellySim(0.55, 2.0, 1.0, 5).monte_carlo(0.02, 52, trials=400, seed=13)
        self.assertGreater(strong["median_final_multiple"],
                           weak["median_final_multiple"])

    def test_the_sweep_marks_the_target_unreachable_within_kelly_at_the_bottom(self):
        # The lowest win rates must not be reported as reachable, or the
        # sensitivity table would be an invitation.
        rows = edge_sensitivity()
        worst = [r for r in rows if r["win_rate"] == 0.35
                 and r["reward_to_risk"] == 1.0]
        self.assertTrue(worst)
        self.assertFalse(worst[0]["target_reachable_within_kelly"])
        self.assertIsNone(worst[0]["risk_per_trade_needed_for_target"])

    def test_every_sweep_row_reports_what_the_2pct_policy_actually_does(self):
        # Whatever the fantasy row says, each must also carry the outcome at
        # the risk this account is allowed to take.
        for r in edge_sensitivity():
            self.assertIn("mc_at_policy_risk_2pct", r)
