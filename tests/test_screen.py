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
from tools.screen import (breakout_at, breakout_now, completed, screen,
                          build_universe, LOOKBACK, ATR_PERIOD, CRITERIA,
                          UNIVERSE_FILE)


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


class TestTheFeedIsNotADetail(unittest.TestCase):
    """M-30. `bars()` was pinned to feed=iex because the free plan was believed
    to serve nothing else. It serves sip. IEX is one venue carrying a median
    3.8% of consolidated volume, and a 3.8% sample does not misprice a mean —
    it misprices an EXTREMUM, which is the only statistic this module uses.

    Measured on 2026-09-22 across 59 universe names, completed sessions:
    ATR(14) IEX/SIP median 0.976, SMALLER IN 59 OF 59; the 20-day high
    understated in 43/59 (worst -0.913%); the 20-day low overstated in 41/59.
    One-directional every time, because a subset of prints cannot contain a
    higher high or a lower low than the whole. One name in 59 showed a
    breakout on IEX that did not exist on the consolidated tape.
    """

    def test_the_current_session_is_not_a_completed_one(self):
        today = dt.date(2026, 1, 21)
        bars = series([10.0] * 21)          # last bar IS today
        self.assertEqual(bars[-1].date, today)
        self.assertEqual(len(completed(bars, today)), 20)
        self.assertTrue(all(b.date < today for b in completed(bars, today)))

    def test_the_level_comes_from_bars_and_the_price_does_not(self):
        # The whole point of the split: a stale bar close must not be able to
        # call a breakout, and a live price must be able to.
        hist = series([10.0] * (LOOKBACK + ATR_PERIOD))
        self.assertIsNone(breakout_now(hist, 9.99))
        b = breakout_now(hist, 10.50)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(b["close"], 10.50)      # the LIVE price
        self.assertAlmostEqual(b["prior_high"], 10.0)  # the level from bars

    def test_an_understated_high_is_what_manufactures_a_phantom(self):
        # RKLB, 2026-09-22: IEX said the 20-day high was 70.56 and the price
        # 70.76, so the screen called a breakout. Consolidated said 71.21 and
        # the trade was 70.05 BELOW the level. Same price, different tape.
        iex_hist = series([60.0] * (LOOKBACK + ATR_PERIOD - 1) + [70.0],
                          highs=[60.0] * (LOOKBACK + ATR_PERIOD - 1) + [70.56])
        sip_hist = series([60.0] * (LOOKBACK + ATR_PERIOD - 1) + [70.0],
                          highs=[60.0] * (LOOKBACK + ATR_PERIOD - 1) + [71.21])
        self.assertIsNotNone(breakout_now(iex_hist, 70.76))   # the phantom
        self.assertIsNone(breakout_now(sip_hist, 70.76))      # the truth

    def test_breakout_at_still_works_on_history(self):
        # base_rate and replay legitimately use a completed bar's own close.
        bars = series([10.0] * (LOOKBACK + ATR_PERIOD) + [12.0])
        b = breakout_at(bars, len(bars) - 1)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(b["close"], 12.0)
        self.assertAlmostEqual(b["prior_high"], 10.0)
        self.assertIsNone(breakout_at(bars, len(bars) - 2))

    def test_no_live_price_stands_the_symbol_down(self):
        # Never fall back to the stale series. A missing price is a refusal.
        class NoPrice:
            def bars(self, sym, limit=250):
                return [{"date": (dt.date.today() - dt.timedelta(days=i)).isoformat(),
                         "open": 10, "high": 10, "low": 10, "close": 10,
                         "volume": 1e6} for i in range(60, 0, -1)]
            def last_trade(self, sym):
                return None
        r = screen(NoPrice(), ["AAPL"])
        self.assertEqual(r["hits"], [])
        self.assertIn("AAPL", r["no_data"])


class TestUniverseIsBuiltFromACompletedSession(unittest.TestCase):
    """M-29. build_universe read `dailyBar`, which during the session is a
    PARTIAL bar. At 09:50 ET that measured twenty minutes of volume against a
    full-day floor, so a $1.5M threshold behaved like ~$30M/day and dropped
    MARA, CMCSA, MNST, ZTS and TFC — all plainly liquid.

    Not merely wrong: not REPRODUCIBLE. The scan walks ~11,800 assets over
    several minutes, so the effective floor moved during a single build. KR
    was excluded while the build ran and passed minutes later.
    """

    class Snap:
        """dailyBar is 1/20th of prevDailyBar — i.e. early in the session."""
        def _request(self, method, url):
            if "/v2/assets" in url:
                return [{"symbol": "LIQD", "tradable": True, "exchange": "NYSE",
                         "name": "Liquid Co"}]
            return {"LIQD": {
                "dailyBar": {"c": 10.0, "v": 20_000, "t": "2026-09-22T04:00:00Z"},
                "prevDailyBar": {"c": 10.0, "v": 400_000, "t": "2026-09-21T04:00:00Z"},
            }}

    def test_a_liquid_name_is_not_dropped_for_the_time_of_day(self):
        # $200k so far today, $4M in the completed session, floor $1.5M.
        u = build_universe(self.Snap(), dict(CRITERIA, min_dollar_volume=1_500_000.0))
        self.assertEqual([r["symbol"] for r in u["symbols"]], ["LIQD"])
        self.assertEqual(u["symbols"][0]["dollar_volume"], 4_000_000)

    def test_the_file_records_which_session_it_measured(self):
        # Without this the universe cannot be checked against anything later.
        u = build_universe(self.Snap(), CRITERIA)
        self.assertEqual(u["liquidity_session"], "2026-09-21")
        self.assertIn("completed session", u["volume_feed"])

    def test_a_stale_name_does_not_relabel_the_whole_file(self):
        """The provenance field is only useful if it is true.

        The first version read whichever symbol the API returned first. A name
        that has not traded in a week carries a week-old prevDailyBar, so two
        builds selecting IDENTICAL universes reported 2026-09-14 and
        2026-09-21. Caught by the reproducibility check written for M-29.
        """
        class Mixed:
            def _request(self, method, url):
                if "/v2/assets" in url:
                    return [{"symbol": s, "tradable": True, "exchange": "NYSE",
                             "name": f"{s} Co"} for s in ("STALE", "A", "B")]
                return {
                    # returned FIRST, and a week out of date
                    "STALE": {"prevDailyBar": {"c": 10.0, "v": 400_000,
                                               "t": "2026-09-14T04:00:00Z"}},
                    "A": {"prevDailyBar": {"c": 10.0, "v": 900_000,
                                           "t": "2026-09-21T04:00:00Z"}},
                    "B": {"prevDailyBar": {"c": 10.0, "v": 800_000,
                                           "t": "2026-09-21T04:00:00Z"}},
                }
        u = build_universe(Mixed(), CRITERIA)
        self.assertEqual(u["liquidity_session"], "2026-09-21")
        self.assertEqual(u["other_sessions_present"], ["2026-09-14"])
