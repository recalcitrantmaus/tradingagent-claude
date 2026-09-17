"""The screen that vetoes trades has to be re-runnable and correct.

Two sessions set posture partly on "zero of N names are above their 20-day
high" from an ad-hoc screen that lived in neither the repo nor a test. The
claim was not reproducible, and the candidate list behind the runner's own
fallback was six hardcoded tickers.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.market import Bar
from tools.screen import breakout_at, LOOKBACK, ATR_PERIOD, CRITERIA, UNIVERSE_FILE


def series(closes, highs=None):
    highs = highs or closes
    return [Bar(dt.date(2026, 1, 1) + dt.timedelta(days=i), c, h, c * 0.98, c, 1_000_000)
            for i, (c, h) in enumerate(zip(closes, highs))]


class TestBreakoutDetection(unittest.TestCase):
    def test_close_above_prior_window_high_is_a_breakout(self):
        bars = series([10.0] * (LOOKBACK + ATR_PERIOD) + [12.0])
        b = breakout_at(bars, len(bars) - 1)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(b["close"], 12.0)
        self.assertAlmostEqual(b["prior_high"], 10.0)

    def test_close_equal_to_the_prior_high_is_not_a_breakout(self):
        """Strictly above. An equal close is a test of the level, not a break."""
        bars = series([10.0] * (LOOKBACK + ATR_PERIOD) + [10.0])
        self.assertIsNone(breakout_at(bars, len(bars) - 1))

    def test_the_breakout_bar_is_excluded_from_its_own_window(self):
        """Off-by-one here makes every bar its own high and fires never."""
        bars = series([10.0] * (LOOKBACK + ATR_PERIOD) + [12.0])
        b = breakout_at(bars, len(bars) - 1)
        self.assertNotAlmostEqual(b["prior_high"], 12.0)

    def test_too_little_history_returns_none_rather_than_guessing(self):
        self.assertIsNone(breakout_at(series([10.0] * 5), 4))

    def test_index_past_the_series_is_none(self):
        bars = series([10.0] * (LOOKBACK + ATR_PERIOD + 1))
        self.assertIsNone(breakout_at(bars, len(bars)))


class TestUniverseCriteria(unittest.TestCase):
    def test_price_ceiling_matches_what_the_engine_can_size(self):
        """At $300 with whole-share sizing, a dearer name always rounds to 0."""
        self.assertLessEqual(CRITERIA["max_price"], 75.0)

    def test_there_is_a_junk_price_floor(self):
        self.assertGreaterEqual(CRITERIA["min_price"], 3.0)

    def test_otc_is_excluded(self):
        self.assertNotIn("OTC", CRITERIA["exchanges"])

    def test_leveraged_products_are_excluded_by_name(self):
        for token in ("2X", "3X"):
            self.assertIn(token, CRITERIA["exclude_name_contains"])

    def test_universe_is_committed_to_the_repo(self):
        """A screen whose inputs are rebuilt per run cannot be audited."""
        self.assertTrue(UNIVERSE_FILE.exists(),
                        "data/universe.json must be committed")
        import json
        u = json.loads(UNIVERSE_FILE.read_text())
        self.assertGreater(u["count"], 50, "six tickers is not a universe")
        for row in u["symbols"]:
            self.assertLessEqual(row["price"], u["criteria"]["max_price"])
            self.assertGreaterEqual(row["price"], u["criteria"]["min_price"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
