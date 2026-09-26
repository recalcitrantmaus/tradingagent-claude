"""The simulator produces the whole evidence base, and had no tests.

Every claim in docs/04 and docs/05 — the 100% lock rate of the target chaser,
the 94% ruin rate without guardrails, the option sleeve being negative at every
capital level, the 4% book cap costing 1% of median — comes out of `run()`. If
it can see the future, or if the guardrails do not actually bind inside it,
those numbers are decoration.

These test the properties that would invalidate every result, not the results
themselves.
"""
import datetime as dt
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.market import SyntheticMarket
from engine.sim import run
from engine.strategies import ALL
from sim.universe import UNIVERSE

SMALL = {"AAA": {"beta": 1.0, "idio_vol": 0.20, "px": 20.0,
                 "asset_class": "equity"}}


class TestTheMarketCannotBeSeenInAdvance(unittest.TestCase):
    """Look-ahead is the one bug that would make every number meaningless,
    and it is invisible in the output — a look-ahead strategy just reports a
    wonderful edge."""

    def test_bars_through_stops_at_the_requested_day(self):
        mkt = SyntheticMarket(SMALL, 60, seed=1)
        for i in (0, 17, 59):
            bars = mkt.bars_through("AAA", i)
            self.assertEqual(len(bars), i + 1)
            self.assertEqual(bars[-1].date, mkt.dates[i])

    def test_bars_through_never_returns_a_future_date(self):
        mkt = SyntheticMarket(SMALL, 40, seed=2)
        cutoff = mkt.dates[20]
        self.assertTrue(all(b.date <= cutoff
                            for b in mkt.bars_through("AAA", 20)))

    def test_the_same_seed_reproduces_the_same_market(self):
        # Without this a sweep compares two different worlds and attributes
        # the difference to the parameter.
        a = SyntheticMarket(SMALL, 30, seed=7)
        b = SyntheticMarket(SMALL, 30, seed=7)
        self.assertEqual([x.close for x in a.history["AAA"]],
                         [x.close for x in b.history["AAA"]])

    def test_different_seeds_produce_different_markets(self):
        a = SyntheticMarket(SMALL, 30, seed=1)
        b = SyntheticMarket(SMALL, 30, seed=2)
        self.assertNotEqual([x.close for x in a.history["AAA"]],
                            [x.close for x in b.history["AAA"]])

    def test_every_bar_is_internally_consistent(self):
        # high >= max(open, close) and low <= min(open, close), or the fill
        # logic can be handed a bar that cannot exist.
        mkt = SyntheticMarket(UNIVERSE, 120, seed=3)
        for sym, bars in mkt.history.items():
            for b in bars:
                self.assertGreaterEqual(b.high, max(b.open, b.close), sym)
                self.assertLessEqual(b.low, min(b.open, b.close), sym)
                self.assertGreater(b.close, 0, sym)

    def test_symbols_are_correlated_because_a_crisis_is_not_diversifiable(self):
        # The universe docstring claims every symbol is beta-loaded onto a
        # common factor. The 4% book cap was chosen against that assumption,
        # so it is pinned: an uncorrelated sim would have understated the cap.
        import statistics
        mkt = SyntheticMarket(UNIVERSE, 260, seed=4)
        eq = [s for s, c in UNIVERSE.items() if c["asset_class"] in ("equity", "etf")]
        rets = {s: [mkt.history[s][i].close / mkt.history[s][i-1].close - 1
                    for i in range(1, len(mkt.history[s]))] for s in eq}
        def corr(x, y):
            ax, ay = rets[x], rets[y]
            mx, my = statistics.mean(ax), statistics.mean(ay)
            num = sum((p-mx)*(q-my) for p, q in zip(ax, ay))
            den = (sum((p-mx)**2 for p in ax) * sum((q-my)**2 for q in ay)) ** 0.5
            return num/den if den else 0.0
        pairs = [corr(x, y) for i, x in enumerate(eq) for y in eq[i+1:]]
        self.assertGreater(statistics.median(pairs), 0.3,
                           "the sim must not be more diversifiable than reality")


class TestTheGuardrailsBindInsideTheSimulator(unittest.TestCase):
    """A sim that reports 0% ruin because the rails are inert proves nothing."""

    def _run(self, name="momentum_breakout", cfg=DEFAULT, seed=0, days=180):
        return run(ALL[name], SyntheticMarket(UNIVERSE, days, seed=seed), cfg)

    def test_the_risk_gate_actually_REFUSES_things_inside_a_run(self):
        """The property that would make every sim number meaningless if it
        failed silently: if `rejections` were always empty, the rails would
        never have bound and 0% ruin would mean nothing.

        SimResult has no max-positions field, so concurrency is asserted
        through the refusal log rather than invented as an attribute — an
        earlier draft of this test asserted `r.max_positions_held` and errored,
        which is the honest reason this is written the way it is.
        """
        seen = {}
        for seed in range(6):
            for reason, n in (self._run(seed=seed).rejections or {}).items():
                seen[reason] = seen.get(reason, 0) + n
        self.assertTrue(seen, "no proposal was ever refused across 6 runs")

    def test_equity_never_goes_negative(self):
        for seed in range(5):
            self.assertGreater(self._run(seed=seed).final_equity, 0.0)

    def test_the_drawdown_lock_is_never_breached_without_locking(self):
        # If a run is down more than the lock threshold it must have LOCKED.
        for seed in range(12):
            r = self._run(seed=seed, days=260)
            if r.max_drawdown > DEFAULT.max_drawdown_lock_pct + 1e-9:
                self.assertEqual(r.end_state, "LOCKED",
                                 f"seed {seed} breached the lock without locking")

    def test_options_are_refused_below_the_equity_floor(self):
        # The double lock in CLAUDE.md: no option sleeve under $1,500.
        r = self._run("option_swing", days=260)
        self.assertEqual(r.trades, 0,
                         "the option sleeve opened below its equity floor")

    def test_the_target_chaser_control_is_still_a_control(self):
        # docs/04's headline: the strategy that pursues +5%/week most directly
        # destroys the account. If this ever stops being true the control has
        # silently stopped controlling anything.
        chaser = [self._run("target_chaser_CONTROL", seed=s, days=260) for s in range(8)]
        disciplined = [self._run("momentum_breakout", seed=s, days=260)
                       for s in range(8)]
        self.assertLess(sum(c.final_equity for c in chaser) / 8,
                        sum(d.final_equity for d in disciplined) / 8)

    def test_removing_the_guardrails_makes_it_worse(self):
        # The ablation docs/05 rests on. If a loosened config were BETTER the
        # rails would be costing us for nothing.
        loose = replace(DEFAULT, max_risk_per_trade_pct=0.25,
                        max_portfolio_risk_pct=1.0,
                        correlated_risk_decay=1.0,
                        max_drawdown_lock_pct=0.99)
        tight = [self._run(seed=s, days=260).final_equity for s in range(10)]
        wild = [self._run(cfg=loose, seed=s, days=260).final_equity
                for s in range(10)]
        self.assertLess(min(wild), min(tight),
                        "unconstrained sizing must produce a worse worst case")


class TestTheTimeStopForTheTargetStudy(unittest.TestCase):
    """D-24 (2026-09-26). The no-target arm exits only on its stop or on a
    holding-period time stop. The sim had no time stop for equities, so the
    arm could not be tested inside the engine at all."""

    def _run(self, strat, cfg, seed=0, days=260):
        return run(strat, SyntheticMarket(UNIVERSE, days, seed=seed), cfg)

    def test_the_time_stop_is_inert_by_default(self):
        a = self._run(ALL["momentum_breakout"], DEFAULT)
        b = self._run(ALL["momentum_breakout"],
                      replace(DEFAULT, max_holding_days=0))
        self.assertEqual(a.equity_curve, b.equity_curve)

    def test_no_position_outlives_the_time_stop(self):
        from engine.strategies import WithoutTarget
        cfg = replace(DEFAULT, require_target=False, max_holding_days=5)
        held, timed = 0, 0
        for seed in range(5):
            r = self._run(WithoutTarget(ALL["momentum_breakout"]), cfg, seed)
            held = max(held, r.max_days_held)
            timed += r.exit_reasons.get("time", 0)
        self.assertLessEqual(held, 5)
        self.assertGreater(timed, 0, "the time stop must actually fire")

    def test_without_target_really_removes_the_target(self):
        from engine.strategies import WithoutTarget
        cfg = replace(DEFAULT, require_target=False, max_holding_days=20)
        r = self._run(WithoutTarget(ALL["momentum_breakout"]), cfg)
        self.assertEqual(r.exit_reasons.get("target", 0), 0)
        self.assertEqual(r.exit_reasons.get("scale_out", 0), 0)
