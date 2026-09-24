"""The research tools, which decide what the strategy BELIEVES.

A bug in `engine/` costs a trade. A bug here costs a rule: the studies in
docs/15, docs/16 and docs/17 are what promoted the 1.5R gate, killed the
structural target and settled chase-vs-retest, and every one of those numbers
came out of `resolve`, `summarise`, `eligible` and
`liquidity_ranked_membership`. If `resolve` filled a gapped stop at the stop
price, every arm would look better than it is and we would size into an edge
that does not exist. So the tests below are mostly about two things:

  1. arithmetic that is easy to get flatteringly wrong (gap fills, which side
     of a tie wins, median vs mean), and
  2. look-ahead — the failure a backtest cannot show you, because it makes the
     results BETTER. Several tests here mutate bars AFTER the signal and
     assert that nothing computed at signal time moved.
"""
import datetime as dt
import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.market import Bar, atr
from tools import entry_study, multiproxy, multiyear, pit_study, proxy_study
from tools.pit_study import classify, eligible, liquidity_ranked_membership
from tools.screen import ATR_PERIOD, LOOKBACK
from tools.target_study import (MA_PERIOD, SWING_K, overhead_levels, resolve,
                                round_step, summarise, target_for)

D0 = dt.date(2025, 1, 1)


def B(i, o, h, l, c, v=1e6):
    return Bar(D0 + dt.timedelta(days=i), o, h, l, c, v)


def flat(n, px=20.0, v=1e6, start=0):
    """n bars at `px` with a 2%-wide range, so ATR is non-zero but tiny."""
    return [B(start + i, px, px * 1.01, px * 0.99, px, v) for i in range(n)]


# A flat series ties on every high, and the pivot test is `>=`, so EVERY bar of
# `flat()` is a swing high at 20.2. Levels are only ever read above the entry,
# so the tests below enter at 20.5 — above that ambient ceiling — and a "swing"
# in the result is then a deliberately-placed pivot rather than the noise floor.
ENTRY = 20.5


# ======================================================================
# resolve() — the R of a single trade. Every study number is a mean of these.
# ======================================================================
class ResolveTests(unittest.TestCase):

    def test_stop_fill_is_the_worse_of_the_stop_and_the_open(self):
        """A gap through the stop is worse than -1R.

        Docstring in target_study calls filling a gapped stop at the stop price
        "the single most flattering error a backtest can make". It is also the
        easiest one to write, so it gets the first test.
        """
        bars = [B(0, 100, 101, 99, 100), B(1, 90, 92, 88, 91)]
        r = resolve(bars, 0, 100.0, 95.0, None, 20)
        self.assertEqual(r["exit"], "stop")
        self.assertAlmostEqual(r["R"], (90 - 100) / 5.0)   # -2.0R, not -1.0R
        self.assertLess(r["R"], -1.0)

    def test_stop_touched_intraday_fills_at_the_stop(self):
        bars = [B(0, 100, 101, 99, 100), B(1, 99, 100, 94, 96)]
        r = resolve(bars, 1, 100.0, 95.0, None, 20)
        self.assertEqual(r["exit"], "stop")
        self.assertAlmostEqual(r["R"], -1.0)

    def test_target_fill_is_the_better_of_the_target_and_the_open(self):
        """Symmetry check: the gap rule must cut both ways, or it is a bias."""
        bars = [B(0, 100, 101, 99, 100), B(1, 120, 121, 119, 120)]
        r = resolve(bars, 1, 100.0, 95.0, 110.0, 20)
        self.assertEqual(r["exit"], "target")
        self.assertAlmostEqual(r["R"], (120 - 100) / 5.0)

    def test_stop_wins_when_one_bar_touches_both(self):
        """Intraday order is unknowable from a daily bar; take the bad one."""
        bars = [B(0, 100, 115, 90, 100)]
        r = resolve(bars, 0, 100.0, 95.0, 110.0, 20)
        self.assertEqual(r["exit"], "stop")

    def test_timeout_exits_at_the_close_of_the_last_bar_in_the_window(self):
        bars = flat(10, 100.0)
        bars[3] = B(3, 100, 101, 99, 104)
        r = resolve(bars, 0, 100.0, 95.0, None, 3)
        self.assertEqual(r["exit"], "timeout")
        self.assertEqual(r["bars"], 3)
        self.assertAlmostEqual(r["R"], (104 - 100) / 5.0)

    def test_horizon_is_clipped_to_the_bars_that_exist(self):
        """A trade opened near the end of the data must not index past it."""
        bars = flat(4, 100.0)
        r = resolve(bars, 2, 100.0, 95.0, None, 20)
        self.assertEqual(r["exit"], "timeout")
        self.assertEqual(r["bars"], 1)

    def test_the_entry_bar_itself_can_stop_the_trade_out(self):
        """resolve walks from entry_i, not entry_i+1: you can be stopped on
        the day you bought. A range starting at entry_i+1 would quietly grant
        every trade one free day."""
        bars = [B(0, 100, 101, 90, 92), B(1, 92, 93, 91, 92)]
        r = resolve(bars, 0, 100.0, 95.0, None, 20)
        self.assertEqual(r["exit"], "stop")
        self.assertEqual(r["bars"], 0)

    def test_nothing_after_the_horizon_is_read(self):
        """Look-ahead guard: a 10x spike one bar past the window changes
        nothing."""
        base = flat(30, 100.0)
        r1 = resolve(base, 0, 100.0, 95.0, 200.0, 5)
        spiked = list(base)
        for k in range(6, 30):
            spiked[k] = B(k, 1000, 1100, 900, 1000)
        r2 = resolve(spiked, 0, 100.0, 95.0, 200.0, 5)
        self.assertEqual(r1, r2)

    def test_R_is_measured_against_entry_minus_stop(self):
        """Two trades with the same dollar move and different stops are not
        the same trade."""
        bars = [B(0, 100, 101, 99, 100), B(1, 100, 110, 99, 110)]
        wide = resolve(bars, 1, 100.0, 90.0, 110.0, 20)
        tight = resolve(bars, 1, 100.0, 95.0, 110.0, 20)
        self.assertAlmostEqual(wide["R"], 1.0)
        self.assertAlmostEqual(tight["R"], 2.0)


# ======================================================================
# levels — where a target comes from, and whether it peeked
# ======================================================================
class LevelTests(unittest.TestCase):

    def test_fine_grid_steps_at_the_documented_boundaries(self):
        self.assertEqual(round_step(50.0), 5.0)
        self.assertEqual(round_step(49.99), 1.0)
        self.assertEqual(round_step(10.0), 1.0)
        self.assertEqual(round_step(9.99), 0.5)

    def test_coarse_grid_steps_at_the_documented_boundaries(self):
        for px, step in ((100.0, 25.0), (99.99, 10.0), (50.0, 10.0),
                         (49.99, 5.0), (20.0, 5.0), (19.99, 1.0),
                         (5.0, 1.0), (4.99, 0.5)):
            self.assertEqual(round_step(px, coarse=True), step, px)

    def test_the_coarse_grid_is_never_finer_than_the_fine_one(self):
        """The coarse grid exists because the fine one bound 68% of signals at
        a median 0.55R — it was a round-number rule in disguise. If any price
        made coarse the tighter of the two, that fix would silently reverse."""
        for px in (3, 4.99, 5, 9.99, 10, 19.99, 20, 49.99, 50, 99.99, 100, 400):
            self.assertGreaterEqual(round_step(float(px), True),
                                    round_step(float(px)), px)

    def test_a_swing_high_is_ignored_until_its_window_has_closed(self):
        """The look-ahead that would matter most. A pivot needs SWING_K bars
        either side; counting one whose right side has not closed means the
        study knows on Monday that Tuesday was lower."""
        bars = flat(40, 20.0)
        bars[30] = B(30, 20, 30.0, 19.8, 20)          # the pivot
        # i = 32: the pivot is 2 bars back, its 3-bar right window is open.
        self.assertNotIn("swing", overhead_levels(bars, 32, ENTRY))
        # i = 33: closed. Same bars, same pivot, now visible.
        self.assertAlmostEqual(overhead_levels(bars, 33, ENTRY)["swing"], 30.0)

    def test_swing_takes_the_nearest_level_above_entry(self):
        bars = flat(60, 20.0)
        bars[20] = B(20, 20, 40.0, 19.8, 20)
        bars[30] = B(30, 20, 25.0, 19.8, 20)
        bars[40] = B(40, 20, 15.0, 10.0, 12)          # below entry: not a level
        self.assertAlmostEqual(overhead_levels(bars, 50, ENTRY)["swing"], 25.0)

    def test_ma200_appears_only_with_200_bars_and_only_when_overhead(self):
        short = flat(MA_PERIOD - 1, 20.0)
        self.assertNotIn("ma200", overhead_levels(short, len(short) - 1, 10.0))
        long = flat(MA_PERIOD + 5, 20.0)
        self.assertAlmostEqual(
            overhead_levels(long, MA_PERIOD - 1, 10.0)["ma200"], 20.0)
        self.assertNotIn("ma200", overhead_levels(long, MA_PERIOD - 1, 25.0))

    def test_the_round_level_is_strictly_above_the_entry(self):
        """Entry sitting exactly on a round number must get the NEXT one, or
        the target is the entry and expected R is 0."""
        lv = overhead_levels(flat(30, 20.0), 29, 20.0)
        self.assertAlmostEqual(lv["round"], 21.0)
        self.assertGreater(lv["round"], 20.0)

    def test_levels_do_not_change_when_the_future_is_rewritten(self):
        """Property test over the whole function: truncating the series at
        i+1 must give the same answer as leaving the future in place."""
        bars = flat(60, 20.0)
        bars[20] = B(20, 20, 26.0, 19.8, 20)
        bars[45] = B(45, 20, 99.0, 19.8, 20)          # after i — must not count
        for coarse in (False, True):
            self.assertEqual(overhead_levels(bars, 40, 20.0, coarse),
                             overhead_levels(bars[:41], 40, 20.0, coarse))

    def test_mechanical_target_is_three_atr_above_entry(self):
        self.assertAlmostEqual(target_for("mechanical", [], 0, 100.0, 2.0), 106.0)

    def test_none_means_no_target(self):
        self.assertIsNone(target_for("none", [], 0, 100.0, 2.0))

    def test_a_variant_only_sees_the_levels_it_names(self):
        bars = flat(MA_PERIOD + 10, 20.0)
        i = MA_PERIOD + 5
        bars[i - 20] = B(i - 20, 20, 26.0, 19.8, 20)   # inside SWING_LOOKBACK
        self.assertAlmostEqual(target_for("struct_swing", bars, i, ENTRY, 1.0),
                               26.0)          # ignores the 21.0 round number
        self.assertAlmostEqual(target_for("structural", bars, i, ENTRY, 1.0),
                               21.0)          # nearest of swing/ma200/round

    def test_nothing_overhead_falls_back_to_the_mechanical_target(self):
        """"No resistance" must not become "no limit" — an unobstructed move
        still needs a number, and the honest one is the mechanical target."""
        bars = flat(30, 20.0)                          # nothing above ENTRY
        t = target_for("struct_swing", bars, 29, ENTRY, 2.0)
        self.assertAlmostEqual(t, ENTRY + 3 * 2.0)


# ======================================================================
# summarise() — the statistics every doc quotes
# ======================================================================
class SummariseTests(unittest.TestCase):

    def rows(self, Rs, exits=None):
        exits = exits or ["timeout"] * len(Rs)
        return [{"R": r, "bars": 5, "exit": e} for r, e in zip(Rs, exits)]

    def test_empty_sample_reports_n_zero_and_nothing_else(self):
        self.assertEqual(summarise([]), {"n": 0})

    def test_expectancy_se_and_t_against_hand_arithmetic(self):
        s = summarise(self.rows([1.0, -1.0, 2.0, 0.0]))
        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["expectancy"], 0.5)
        self.assertAlmostEqual(s["sd"], statistics.pstdev([1.0, -1.0, 2.0, 0.0]))
        self.assertAlmostEqual(s["se"], s["sd"] / 2)
        self.assertAlmostEqual(s["t"], 0.5 / s["se"])
        self.assertAlmostEqual(s["total_R"], 2.0)
        self.assertAlmostEqual(s["median_R"], 0.5)
        self.assertAlmostEqual(s["best"], 2.0)
        self.assertAlmostEqual(s["worst"], -1.0)

    def test_a_scratch_trade_is_not_a_win(self):
        """R == 0 lands in avg_loss, not win_rate. Counting it as a win would
        flatter every arm by the same amount and change which one wins."""
        s = summarise(self.rows([1.0, 0.0]))
        self.assertAlmostEqual(s["win_rate"], 0.5)
        self.assertAlmostEqual(s["avg_win"], 1.0)
        self.assertAlmostEqual(s["avg_loss"], 0.0)

    def test_avg_loss_is_zero_when_nothing_lost(self):
        s = summarise(self.rows([1.0, 2.0]))
        self.assertAlmostEqual(s["win_rate"], 1.0)
        self.assertAlmostEqual(s["avg_loss"], 0.0)

    def test_t_is_zero_rather_than_infinite_on_a_single_trade(self):
        s = summarise(self.rows([1.0]))
        self.assertEqual(s["se"], 0.0)
        self.assertEqual(s["t"], 0.0)

    def test_the_exit_counts_account_for_every_trade(self):
        """If a new exit kind is ever added, this fails instead of silently
        dropping those trades out of the printed breakdown."""
        s = summarise(self.rows([1.0, -1.0, 0.5],
                                ["target", "stop", "timeout"]))
        self.assertEqual(sum(s["exits"].values()), s["n"])


# ======================================================================
# the universe — which names were investable, on the day
# ======================================================================
class UniverseTests(unittest.TestCase):

    def test_leveraged_is_decided_before_inverse(self):
        """"ULTRASHORT S&P500" matches both lists. It is a 2x product and
        must not be classified as a plain inverse fund, which is the only
        downside vehicle the rules allow."""
        self.assertEqual(classify("ProShares UltraShort S&P500"), "leveraged")
        self.assertEqual(classify("Direxion Daily 3X Bull"), "leveraged")
        self.assertEqual(classify("ProShares Short S&P500"), "inverse")
        self.assertEqual(classify("Apple Inc"), "plain")

    def test_classification_ignores_case(self):
        self.assertEqual(classify("proshares short s&p500"), "inverse")

    def test_the_price_band_is_inclusive_at_both_ends(self):
        def at(px):
            bars = flat(25, px, v=1e6)
            return eligible(bars, 24)
        self.assertTrue(at(pit_study.MIN_PX))
        self.assertTrue(at(pit_study.MAX_PX))
        self.assertFalse(at(pit_study.MIN_PX - 0.01))
        self.assertFalse(at(pit_study.MAX_PX + 0.01))

    def test_liquidity_uses_the_median_so_one_busy_day_cannot_qualify_a_name(self):
        """A dead name with a single earnings-day print has a mean dollar
        volume above the floor and a median far below it. Using the mean would
        put un-exitable names in the universe, and the study would show trades
        the account could never have made."""
        px = 20.0
        bars = flat(25, px, v=1_000)                   # $20k/day: nowhere near
        bars[24] = B(24, px, px * 1.01, px * 0.99, px, 1e9)   # one $20bn day
        self.assertGreater(statistics.mean(b.close * b.volume for b in bars[5:25]),
                           pit_study.MIN_DV)
        self.assertFalse(eligible(bars, 24))

    def test_liquidity_reads_the_trailing_twenty_bars_only(self):
        px = 20.0
        bars = flat(40, px, v=1e9)                     # liquid long ago
        for i in range(20, 40):
            bars[i] = B(i, px, px * 1.01, px * 0.99, px, 1_000)   # dead since
        self.assertFalse(eligible(bars, 39))

    def test_membership_keeps_only_the_most_liquid_names_that_day(self):
        raw, names = {}, {}
        for n, vol in (("AAA", 9e6), ("BBB", 8e6), ("CCC", 7e6), ("DDD", 6e6)):
            raw[n] = [["2025-03-%02d" % (d + 1), 20, 20, 20, 20.0, vol]
                      for d in range(25)]
            names[n] = "%s Inc" % n
        m = liquidity_ranked_membership(raw, names, "plain", 2025, 2)
        self.assertEqual(m["2025-03-25"], {"AAA", "BBB"})

    def test_membership_is_recomputed_for_every_date(self):
        """The whole point of the point-in-time universe. A name that was
        liquid in March and dead in April must be in March's set and out of
        April's — a single snapshot is the survivorship bug this replaced."""
        days = ([("2025-03-%02d" % (d + 1), 9e6) for d in range(25)]
                + [("2025-04-%02d" % (d + 1), 1_000) for d in range(25)])
        raw = {"AAA": [[d, 20, 20, 20, 20.0, v] for d, v in days],
               "BBB": [[d, 20, 20, 20, 20.0, 5e6] for d, _ in days]}
        names = {"AAA": "A Inc", "BBB": "B Inc"}
        m = liquidity_ranked_membership(raw, names, "plain", 2025, 1)
        self.assertEqual(m["2025-03-25"], {"AAA"})     # AAA the more liquid
        self.assertEqual(m["2025-04-25"], {"BBB"})     # AAA has dropped out

    def test_membership_respects_the_requested_class(self):
        raw = {"AAA": [["2025-03-%02d" % (d + 1), 20, 20, 20, 20.0, 9e6]
                       for d in range(25)]}
        names = {"AAA": "ProShares Short S&P500"}
        self.assertEqual(liquidity_ranked_membership(raw, names, "plain",
                                                     2025, 5), {})
        self.assertEqual(
            liquidity_ranked_membership(raw, names, "inverse", 2025, 5)
            ["2025-03-25"], {"AAA"})


# ======================================================================
# the studies end to end, on bars whose answer is known by construction
# ======================================================================
N = 300
SIG = 240                 # signal bar; entry is SIG+1


def synth(signal_close=21.0, override=None, px=20.0, vol=1e6):
    """A flat $20 name with exactly one 20-day breakout, at index SIG.

    Flat means prior_high is px*1.01 everywhere, so `signal_close` above that
    is the only signal in the series, and the 20 bars after it keep the window
    poisoned so no second one appears.
    """
    rows = []
    for i in range(N):
        c = signal_close if i == SIG else px
        o, h, l = c, c * 1.01, c * 0.99
        if override and i in override:
            o, h, l, c = override[i]
        rows.append([(D0 + dt.timedelta(days=i)).isoformat(), o, h, l, c, vol])
    return {"names": {"AAA": "A Inc"}, "bars": {"AAA": rows}}


def held_above(first, last):
    """Bars whose LOW never reaches the broken 20.2 level, and whose close
    stays under the signal bar's high so no second breakout is created."""
    return {i: (20.6, 20.8, 20.3, 20.6) for i in range(first, last)}


def rewrite_future(first, last):
    """Bars that change the OUTCOME of the trade without changing anything
    visible at signal time, and without triggering a new signal."""
    return {i: (20.5, 20.7, 20.25, 20.5) for i in range(first, last)}


def as_bars(blob, sym="AAA"):
    return [Bar(dt.date.fromisoformat(r[0]), r[1], r[2], r[3], r[4], r[5])
            for r in blob["bars"][sym]]


class EntryStudyTests(unittest.TestCase):

    def test_one_constructed_breakout_produces_exactly_one_signal(self):
        r = entry_study.run(2025, 20, 5, 0, blob=synth())
        self.assertEqual(r["signals"], 1)
        self.assertEqual(len(r["rows"]["chase"]), 1)
        self.assertEqual(r["rows"]["chase"][0]["symbol"], "AAA")

    def test_a_breakout_that_never_comes_back_is_forgone_by_the_retest_arm(self):
        """The finding the whole study exists to measure: the retest rule is
        absent from the signals that never pull back, and those are the ones
        it most wanted."""
        blob = synth(override=held_above(SIG + 1, SIG + 40))
        r = entry_study.run(2025, 20, 5, 0, blob=blob)
        self.assertEqual(r["signals"], 1)
        self.assertEqual(len(r["rows"]["chase"]), 1)
        self.assertEqual(len(r["rows"]["retest"]), 0)
        self.assertEqual(len(r["missed"]), 1)
        self.assertEqual(r["missed"][0], r["rows"]["chase"][0])

    def test_the_wait_window_is_exactly_wait_sessions(self):
        """Off-by-one here silently changes the fill rate, which is the
        headline number of docs/16."""
        # holds above the level for 3 sessions, returns on the 4th
        blob = synth(override=held_above(SIG + 1, SIG + 4))
        self.assertEqual(len(entry_study.run(2025, 20, 3, 0, blob=blob)
                             ["rows"]["retest"]), 0)
        self.assertEqual(len(entry_study.run(2025, 20, 4, 0, blob=blob)
                             ["rows"]["retest"]), 1)

    def test_the_retest_never_pays_more_than_the_broken_level(self):
        """A limit resting at the level cannot fill above it. Here the bar
        OPENS above the level and trades back through it, so the fill is the
        level — paying the open would be paying up for a limit order."""
        blob = synth(override={SIG + 1: (20.6, 20.8, 20.0, 20.5)})
        bars = as_bars(blob)
        a = atr(bars[:SIG + 1], ATR_PERIOD)
        ph = max(b.high for b in bars[SIG - LOOKBACK:SIG])
        e2 = min(ph, bars[SIG + 1].open)
        self.assertAlmostEqual(e2, ph)                 # capped by the level
        s2 = max(e2 - 1.5 * a, e2 * 0.92)
        r = entry_study.run(2025, 20, 5, 0, blob=blob)
        self.assertEqual(len(r["rows"]["retest"]), 1)
        self.assertAlmostEqual(r["rows"]["retest"][0]["R"],
                               resolve(bars, SIG + 1, e2, s2, None, 20)["R"])

    def test_missed_is_never_larger_than_the_chase_arm(self):
        """`missed` is chase's own rows re-filtered, so it cannot exceed it —
        the invariant that makes the decomposition in multiyear valid."""
        blob = synth(override=held_above(SIG + 1, SIG + 40))
        r = entry_study.run(2025, 20, 5, 0, blob=blob)
        self.assertLessEqual(len(r["missed"]), len(r["rows"]["chase"]))

    def test_a_signal_outside_the_study_year_is_not_counted(self):
        self.assertEqual(entry_study.run(2024, 20, 5, 0, blob=synth())
                         ["signals"], 0)


class ProxyStudyTests(unittest.TestCase):

    FEATS = ("breakout_%", "gap_%", "rel_volume", "dist_50ma_%",
             "dist_200ma_%", "atr_%")

    def test_features_do_not_move_when_the_future_is_rewritten(self):
        """The module's central claim, tested rather than asserted: every
        feature comes from bars[:i+1]. Rewriting everything from the entry bar
        onward may change the label and the return; it must not touch a single
        feature."""
        base = proxy_study.run(2025, 5, 0, 20, blob=synth())
        moved = proxy_study.run(2025, 5, 0, 20,
                                blob=synth(override=rewrite_future(SIG + 2,
                                                                   SIG + 40)))
        self.assertEqual(len(base), 1)
        self.assertEqual(len(moved), 1)
        for f in self.FEATS:
            self.assertAlmostEqual(base[0][f], moved[0][f], places=12, msg=f)
        self.assertNotEqual(base[0]["chase_R"], moved[0]["chase_R"])

    def test_breakout_pct_measures_the_close_against_the_prior_high(self):
        rows = proxy_study.run(2025, 5, 0, 20, blob=synth(signal_close=21.0))
        self.assertAlmostEqual(rows[0]["breakout_%"],
                               (21.0 - 20.2) / 20.2 * 100)

    def test_the_label_uses_the_same_wait_window_as_the_entry_study(self):
        blob = synth(override=held_above(SIG + 1, SIG + 4))
        self.assertEqual(proxy_study.run(2025, 3, 0, 20, blob=blob)[0]
                         ["no_pullback"], 1)
        self.assertEqual(proxy_study.run(2025, 4, 0, 20, blob=blob)[0]
                         ["no_pullback"], 0)

    def test_chase_R_is_the_same_number_resolve_would_give(self):
        blob = synth()
        bars = as_bars(blob)
        a = atr(bars[:SIG + 1], ATR_PERIOD)
        e = bars[SIG + 1].open
        s = max(e - 1.5 * a, e * 0.92)
        self.assertAlmostEqual(proxy_study.run(2025, 5, 0, 20, blob=blob)[0]
                               ["chase_R"],
                               resolve(bars, SIG + 1, e, s, None, 20)["R"])

    def test_every_named_feature_is_actually_emitted(self):
        """FEATURES drives the printed report; a key present there and absent
        from the row would raise at print time, after a long study run."""
        row = proxy_study.run(2025, 5, 0, 20, blob=synth())[0]
        for f in proxy_study.FEATURES:
            self.assertIn(f, row)


# ======================================================================
# the multi-year wrappers
# ======================================================================
class MultiYearTests(unittest.TestCase):

    def test_pooled_concatenates_every_year_in_order(self):
        self.assertEqual(multiyear.pooled([[1, 2], [], [3]]), [1, 2, 3])

    def test_pooled_of_nothing_is_empty(self):
        self.assertEqual(multiyear.pooled([]), [])

    def test_quintiles_are_sorted_ascending_by_the_feature(self):
        rows = [{"x": v} for v in (5, 1, 4, 2, 3)]
        qs = multiproxy.q_split(rows, "x", k=5)
        self.assertEqual([q[0]["x"] for q in qs], [1, 2, 3, 4, 5])

    def test_the_remainder_lands_in_the_top_quintile(self):
        """23 rows split 4/4/4/4/7. Dropping the remainder instead would quietly
        discard the most extreme rows — the ones the whole test is about."""
        qs = multiproxy.q_split([{"x": i} for i in range(23)], "x", k=5)
        self.assertEqual([len(q) for q in qs], [4, 4, 4, 4, 7])
        self.assertEqual(sum(len(q) for q in qs), 23)

    def test_quintiles_never_lose_or_duplicate_a_row(self):
        for n in range(5, 40):
            qs = multiproxy.q_split([{"x": i} for i in range(n)], "x", k=5)
            self.assertEqual(sorted(r["x"] for q in qs for r in q),
                             list(range(n)), n)


if __name__ == "__main__":
    unittest.main()
