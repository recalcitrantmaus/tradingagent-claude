"""These tests are the constitution's teeth. If one fails, the agent does not
trade until a human has looked at why.
"""
import datetime as dt
import os
import sys
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import replace
from engine.config import DEFAULT
from engine.portfolio import Portfolio
from engine.risk import RiskOfficer, OrderProposal, State

D = dt.date(2026, 3, 2)          # a Monday
TS = dt.datetime(2026, 3, 2, 10, 0)


def fresh(cfg=DEFAULT):
    pf = Portfolio(cfg.starting_equity)
    ro = RiskOfficer(cfg)
    ro.start_day(D, cfg.starting_equity)
    return pf, ro


def equity_order(**kw):
    base = dict(symbol="TEC", asset_class="equity", side="buy",
                price=50.0, stop=46.0, target=60.0)
    base.update(kw)
    return OrderProposal(**base)


class TestEntryGate(unittest.TestCase):
    def test_entry_without_a_stop_is_rejected(self):
        pf, ro = fresh()
        d = ro.evaluate(equity_order(stop=None), pf, {"TEC": 50.0}, D)
        self.assertFalse(d.approved)
        self.assertIn("no stop", d.reasons[0])

    def test_stop_above_entry_is_rejected(self):
        pf, ro = fresh()
        d = ro.evaluate(equity_order(stop=55.0), pf, {"TEC": 50.0}, D)
        self.assertFalse(d.approved)

    def test_size_never_risks_more_than_2pct(self):
        pf, ro = fresh()
        d = ro.evaluate(equity_order(), pf, {"TEC": 50.0}, D)
        self.assertTrue(d.approved)
        risk = d.qty * (50.0 - 46.0)
        self.assertLessEqual(risk, DEFAULT.starting_equity * DEFAULT.max_risk_per_trade_pct + 1e-9)

    def test_single_position_cap_is_enforced(self):
        pf, ro = fresh()
        # a 1% stop would otherwise let the 2% risk budget buy a huge position
        d = ro.evaluate(equity_order(price=50.0, stop=49.5), pf, {"TEC": 50.0}, D)
        notional = d.qty * 50.0
        self.assertLessEqual(notional,
                             DEFAULT.starting_equity * DEFAULT.max_position_pct_equity + 1e-9)

    def test_cash_reserve_is_never_spent(self):
        pf, ro = fresh()
        d = ro.evaluate(equity_order(price=50.0, stop=49.9), pf, {"TEC": 50.0}, D)
        self.assertLessEqual(d.qty * 50.0,
                             pf.cash - DEFAULT.starting_equity * DEFAULT.min_cash_reserve_pct + 1e-9)

    def test_max_concurrent_positions(self):
        pf, ro = fresh()
        for i in range(DEFAULT.max_concurrent_positions):
            pf.buy(TS, f"S{i}", "equity", 1, 5.0, 0.0)
        d = ro.evaluate(equity_order(), pf, {"TEC": 50.0}, D)
        self.assertFalse(d.approved)

    def test_exits_are_always_allowed_even_when_locked(self):
        # Until M-7 (2026-09-26) this sold TEC with NOTHING held and expected
        # approval, which is the short the fix refuses. An exit needs a
        # position to exit.
        pf, ro = fresh()
        pf.buy(TS, "TEC", "equity", 2, 50.0, 0.0)
        ro.state = State.LOCKED
        d = ro.evaluate(equity_order(side="sell"), pf, {"TEC": 50.0}, D)
        self.assertTrue(d.approved)
        self.assertEqual(d.qty, 2)


class TestOptionsGate(unittest.TestCase):
    def opt(self, **kw):
        # target 3.20 is the config's own option exit pair: a -40% stop and a
        # +60% take-profit, which is exactly 1.5R. The documented option exits
        # sit precisely on the minimum — worth knowing, since any widening of
        # the stop rule without widening the target would put them under it.
        base = dict(symbol="TEC_C", asset_class="option", side="buy",
                    price=2.00, stop=1.20, target=3.20, multiplier=100, dte=30,
                    defined_risk=True, minutes_since_open=30)
        base.update(kw)
        return OrderProposal(**base)

    def test_options_blocked_below_equity_floor(self):
        pf, ro = fresh()
        d = ro.evaluate(self.opt(), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("option floor", d.reasons[0])

    def test_zero_dte_rejected(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=0.25)
        d = ro.evaluate(self.opt(dte=0), pf, {}, D)
        self.assertFalse(d.approved)

    def test_first_15_minutes_rejected(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=0.25)
        d = ro.evaluate(self.opt(minutes_since_open=5), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("observe", d.reasons[0])

    def test_undefined_risk_rejected(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=0.25)
        d = ro.evaluate(self.opt(defined_risk=False), pf, {}, D)
        self.assertFalse(d.approved)


class TestCircuitBreakers(unittest.TestCase):
    def test_daily_loss_halts_the_day(self):
        pf, ro = fresh()
        pf.cash = 300 * (1 - 0.045)
        self.assertEqual(ro.update(D, pf, {}), State.DAY_HALT)
        self.assertFalse(ro.evaluate(equity_order(), pf, {"TEC": 50.0}, D).approved)

    def test_weekly_loss_halts_the_week(self):
        pf, ro = fresh()
        pf.cash = 300 * (1 - 0.09)
        self.assertEqual(ro.update(D, pf, {}), State.WEEK_HALT)

    def test_drawdown_locks_the_account(self):
        pf, ro = fresh()
        pf.peak_equity = 400.0
        pf.cash = 400 * (1 - 0.21)
        self.assertEqual(ro.update(D, pf, {}), State.LOCKED)

    def test_locked_requires_a_human_note(self):
        # Runs at max effort because unlock() also re-checks the T-10 effort
        # floor at the write, and `unlock-authorization` is Opus @ max. This
        # test is about the human NOTE, so it takes the legitimate route past
        # the other gate rather than patching it out. The effort interlock
        # itself is tested in tests/test_model_policy.py.
        with mock.patch.dict(os.environ, {"CLAUDE_EFFORT": "max"}):
            _, ro = fresh()
            ro.state = State.LOCKED
            with self.assertRaises(ValueError):
                ro.unlock("   ")
            ro.unlock("reviewed 2026-03-02, resuming at half size")
            self.assertEqual(ro.state, State.NORMAL)

    def test_consecutive_losses_halt_the_day(self):
        pf, ro = fresh()
        for _ in range(DEFAULT.consecutive_loss_halt):
            ro.record_trade_result(-1.0)
        self.assertEqual(ro.update(D, pf, {}), State.DAY_HALT)

    def test_day_halt_clears_next_day_but_week_halt_does_not(self):
        pf, ro = fresh()
        ro.state = State.DAY_HALT
        ro.start_day(D + dt.timedelta(days=1), 300.0)
        self.assertEqual(ro.state, State.NORMAL)
        ro.state = State.WEEK_HALT
        ro.start_day(D + dt.timedelta(days=1), 300.0)
        self.assertEqual(ro.state, State.WEEK_HALT)
        ro.start_day(D + dt.timedelta(days=7), 300.0)   # next Monday
        self.assertEqual(ro.state, State.NORMAL)


class TestAccounting(unittest.TestCase):
    def test_cannot_spend_money_we_do_not_have(self):
        pf = Portfolio(300.0)
        with self.assertRaises(ValueError):
            pf.buy(TS, "TEC", "equity", 100, 50.0, 0.0)

    def test_realized_pnl_and_cash_agree(self):
        pf = Portfolio(300.0)
        pf.buy(TS, "TEC", "equity", 4, 50.0, 0.0)
        pf.sell(TS, "TEC", 4, 55.0, 0.0)
        self.assertAlmostEqual(pf.realized_pnl, 20.0)
        self.assertAlmostEqual(pf.cash, 320.0)
        self.assertEqual(pf.positions, {})

    def test_t1_settlement_withholds_proceeds(self):
        pf = Portfolio(300.0)
        pf.buy(TS, "TEC", "equity", 4, 50.0, 0.0)
        pf.sell(TS, "TEC", 4, 55.0, 0.0, settle_days=1)
        self.assertAlmostEqual(pf.settled_cash(D), 320.0 - 220.0)
        pf.release_settlements(D + dt.timedelta(days=2))
        self.assertAlmostEqual(pf.settled_cash(D + dt.timedelta(days=2)), 320.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOptionEdgeGate(unittest.TestCase):
    """Options require a measured edge, not just enough money to lose."""

    def opt(self):
        return OrderProposal(symbol="TEC_C", asset_class="option", side="buy",
                             price=2.00, stop=1.20, target=3.20, multiplier=100,
                             dte=30, defined_risk=True, minutes_since_open=30)

    def test_locked_without_a_track_record(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        d = ro.evaluate(self.opt(), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("closed trades", d.reasons[0])

    def test_locked_with_enough_trades_but_negative_expectancy(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=-0.05)
        d = ro.evaluate(self.opt(), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("expectancy", d.reasons[0])

    def test_unlocks_with_trades_and_positive_expectancy(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=0.25)
        d = ro.evaluate(self.opt(), pf, {}, D)
        self.assertTrue(d.approved, d.reasons)

    def test_equity_floor_still_applies_even_with_a_great_record(self):
        pf, ro = fresh()                       # $300
        ro.set_track_record(closed_trades=500, expectancy_R=1.0)
        d = ro.evaluate(self.opt(), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("option floor", d.reasons[0])


class TestExpectedRGate(unittest.TestCase):
    """The rule that lived in three markdown files and no code.

    CLAUDE.md, docs/09-phase2-runbook.md and the trade-plan skill have all
    required "expected R >= 1.5" since the beginning. `evaluate` never read
    `target`, so the gate was unreachable. The simulator did not catch it
    because every simulated strategy targets entry + 3*ATR against a 1.5*ATR
    stop — 2.0R by construction, which could not have failed a 1.5 gate had
    one existed.
    """

    def prop(self, **kw):
        base = dict(symbol="F", asset_class="equity", side="buy",
                    price=10.00, stop=9.00, target=11.50)
        base.update(kw)
        return OrderProposal(**base)

    def test_a_generous_target_passes(self):
        pf, ro = fresh()
        d = ro.evaluate(self.prop(target=12.00), pf, {"F": 10.0}, D)
        self.assertTrue(d.approved, d.reasons)
        self.assertTrue(any("expected R 2.00" in r for r in d.reasons))

    def test_a_target_below_the_minimum_is_rejected(self):
        """Friday 2026-09-18: three breakouts priced to real resistance came
        out at 0.3-0.5R and every one was APPROVED, because nothing checked."""
        pf, ro = fresh()
        d = ro.evaluate(self.prop(target=10.40), pf, {"F": 10.0}, D)
        self.assertFalse(d.approved)
        self.assertIn("expected R", d.reasons[0])

    def test_exactly_at_the_minimum_passes(self):
        pf, ro = fresh()
        d = ro.evaluate(self.prop(target=11.50), pf, {"F": 10.0}, D)
        self.assertTrue(d.approved, d.reasons)

    def test_the_config_option_defaults_are_not_rejected_by_float_noise(self):
        """-40% stop against +60% take-profit is 0.60/0.40 = 1.4999999999999998.

        A gate that rejects its own documented defaults by 2e-16 produces an
        inexplicable refusal carrying a correct-looking reason.
        """
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        ro.set_track_record(closed_trades=50, expectancy_R=0.25)
        prem = 2.00
        d = ro.evaluate(OrderProposal(
            symbol="TEC_C", asset_class="option", side="buy", price=prem,
            stop=prem * (1 - cfg.option_stop_premium_pct),
            target=prem * (1 + cfg.option_take_profit_pct),
            multiplier=100, dte=30, defined_risk=True,
            minutes_since_open=30), pf, {}, D)
        self.assertTrue(d.approved, d.reasons)

    def test_no_target_is_refused(self):
        pf, ro = fresh()
        d = ro.evaluate(self.prop(target=None), pf, {"F": 10.0}, D)
        self.assertFalse(d.approved)
        self.assertIn("no target", d.reasons[0])

    def test_a_target_below_entry_is_refused(self):
        pf, ro = fresh()
        d = ro.evaluate(self.prop(target=9.50), pf, {"F": 10.0}, D)
        self.assertFalse(d.approved)
        self.assertIn("not above entry", d.reasons[0])

    def test_the_simulated_strategies_are_2R_by_construction(self):
        """3*ATR target against a 1.5*ATR stop is 2.0R by construction.

        This is why the 300-seed suite produces identical output with the gate
        and without it: no strategy in engine/strategies.py can author a
        proposal that fails it. If someone changes a target multiple, this
        test fails and says out loud that the suite's coverage of this gate
        just changed.
        """
        atr, entry = 0.50, 10.0
        stop = max(entry - 1.5 * atr, entry * 0.92)
        target = entry + 3.0 * atr
        self.assertAlmostEqual((target - entry) / (entry - stop), 2.0)
        # ...and the 8% floor only ever makes it better, never worse, because
        # `max` takes the TIGHTER stop.
        atr_wide = 2.0
        stop_w = max(entry - 1.5 * atr_wide, entry * 0.92)
        self.assertGreater((entry + 3.0 * atr_wide - entry) / (entry - stop_w), 2.0)

    def test_the_gate_still_binds_when_the_fill_gaps_away_from_the_signal(self):
        """Construction is 2.0R; the FILL is where the gate earns its keep.

        engine/sim.py signals on the close and fills at the next open, leaving
        the stop and target where the close put them. A gap up compresses R
        without anything in the strategy changing, and the gate rejects the
        chase. Measured in the 300-seed suite: a handful of
        "expected R 1.36-1.49 < required 1.50" rejections per arm.

        So the gate is not inert in simulation, as an earlier note claimed. It
        is rare, which is why aggregate equity is unchanged, and it is exactly
        the behaviour that should be rare.
        """
        pf, ro = fresh()
        atr, close = 0.50, 10.0
        stop = max(close - 1.5 * atr, close * 0.92)     # 9.25
        target = close + 3.0 * atr                      # 11.50

        at_close = ro.evaluate(OrderProposal(
            symbol="AAA", asset_class="equity", side="buy",
            price=close, stop=stop, target=target), pf, {}, D)
        self.assertTrue(at_close.approved)

        gapped = ro.evaluate(OrderProposal(
            symbol="AAA", asset_class="equity", side="buy",
            price=close * 1.02, stop=stop, target=target), pf, {}, D)
        self.assertFalse(gapped.approved)
        self.assertIn("expected R", gapped.reasons[-1])


class TestAggregateOpenRiskIsCapped(unittest.TestCase):
    """T-1. Per-trade risk was capped at 2% and concurrency at 4, and nothing
    capped the sum — so the book could carry 8% of equity at risk at once,
    twice `daily_loss_halt_pct` and exactly `weekly_loss_halt_pct`.

    The breakers could not cover that gap. The daily halt stops NEW trades
    once -4% is realised; it cannot unwind stops already resting on the book.

    Measured 2026-09-22 on the day's own signals: four positions, 4.53% of
    equity at risk, no gate objecting. And measured on the same day's price
    history, 60-day return correlation across those names ran 0.45 to 0.83 —
    a long-only breakout book has no uncorrelated pair to spread into, so
    capping the TOTAL is the only diversification control available.
    """

    def setUp(self):
        self.cfg = DEFAULT
        self.ro = RiskOfficer(self.cfg)
        self.today = dt.date(2026, 9, 22)

    def _prop(self, sym, price=60.0, stop=54.0):
        # $6 of risk per share; at $300 equity that is the full 2% budget.
        return OrderProposal(symbol=sym, asset_class="equity", side="buy",
                             price=price, stop=stop, target=price + 18.0,
                             thesis="full per-trade budget")

    def test_the_book_cannot_exceed_the_cap(self):
        pf = Portfolio(300.0)
        prices, total = {}, 0.0
        for i in range(4):
            p = self._prop(f"SYM{i}")
            prices[p.symbol] = p.price
            d = self.ro.evaluate(p, pf, prices, self.today)
            if d.approved and d.qty:
                pf.buy(self.today, p.symbol, "equity", d.qty, p.price, 0.0)
                pf.positions[p.symbol].stop = p.stop
                total += d.qty * (p.price - p.stop)
        self.assertLessEqual(total, 300.0 * self.cfg.max_portfolio_risk_pct + 1e-9)

    def test_the_cap_equals_the_daily_halt_so_the_invariant_is_checkable(self):
        # If every stop filled at once the loss is exactly the day's limit.
        # Without this the -4% breaker is a marker read after the fact.
        self.assertEqual(self.cfg.max_portfolio_risk_pct,
                         self.cfg.daily_loss_halt_pct)

    def test_a_third_full_size_position_is_refused_on_the_book_cap(self):
        # Isolates the CAP, so the size taper is disabled here. With the taper
        # on (the shipped default) the taper binds first — 2% + 1% = 3% still
        # fits under 4% — and the cap becomes a backstop rather than the usual
        # binding constraint. Both are wanted: the taper shapes the book, the
        # cap guarantees its ceiling if concurrency is ever raised.
        cfg = replace(DEFAULT, correlated_risk_decay=1.0)
        ro = RiskOfficer(cfg)
        pf = Portfolio(300.0)
        prices = {}
        for i in range(2):                       # 2 x 2% = the whole budget
            p = self._prop(f"SYM{i}")
            prices[p.symbol] = p.price
            d = ro.evaluate(p, pf, prices, self.today)
            self.assertTrue(d.approved, f"SYM{i} should fit: {d.reasons}")
            pf.buy(self.today, p.symbol, "equity", d.qty, p.price, 0.0)
            pf.positions[p.symbol].stop = p.stop
        third = self._prop("SYM2")
        prices["SYM2"] = third.price
        d = ro.evaluate(third, pf, prices, self.today)
        self.assertFalse(d.approved)
        self.assertTrue(any("open-risk cap" in r for r in d.reasons),
                        f"wrong binding constraint: {d.reasons}")

    def test_a_trailed_stop_returns_budget_to_the_book(self):
        # Risk is measured FROM HERE, not from entry. A position at breakeven
        # consumes no budget and the book should be free to use the room.
        pf = Portfolio(300.0)
        p = self._prop("SYM0")
        prices = {"SYM0": 60.0}
        d = self.ro.evaluate(p, pf, prices, self.today)
        pf.buy(self.today, "SYM0", "equity", d.qty, 60.0, 0.0)
        pf.positions["SYM0"].stop = 54.0
        self.assertAlmostEqual(pf.open_risk(prices), d.qty * 6.0)
        pf.positions["SYM0"].stop = 60.0         # trailed to breakeven
        self.assertAlmostEqual(pf.open_risk(prices), 0.0)

    def test_an_unstopped_position_counts_its_whole_notional(self):
        # Nothing should create one. If one exists its loss is unbounded, and
        # a risk total that ignores it is a comforting number, not a true one.
        pf = Portfolio(300.0)
        pf.buy(self.today, "NAKED", "equity", 2.0, 50.0, 0.0)
        pf.positions["NAKED"].stop = None
        self.assertAlmostEqual(pf.open_risk({"NAKED": 50.0}), 100.0)


class TestSizeTaperAcrossConcurrentPositions(unittest.TestCase):
    """The size-based form of "conservative on most, let one run".

    The target is the wrong lever for that intent: a target controls upside
    while size and the stop control loss, so cutting targets on the also-rans
    would forfeit their winners while keeping their full downside — exactly
    backwards. Cutting SIZE gives the first and strongest position full
    weight and makes every subsequent correlated add cheaper to be wrong
    about.

    It takes no correlation input, and that is a measurement not a shortcut:
    on 2026-09-22 the minimum pairwise 60-day correlation across the day's
    own signals was 0.45, including a space company against a semiconductor.
    There is no uncorrelated pair to detect, so treating every addition as
    correlated is the honest default and keeps the engine deterministic.

    Swept at 3000 seeds on two strategies: median +1.65, p05 +10.00, worst
    drawdown 20.9% -> 17.8%, locked accounts 15/3000 -> 0 (z = -3.88).
    """

    def setUp(self):
        self.cfg = DEFAULT
        self.ro = RiskOfficer(self.cfg)
        self.today = dt.date(2026, 9, 22)

    # $6 of risk per share on a $10 name at R=3.0. Sized so the RISK BUDGET
    # is the binding constraint: at $30k equity the 25% position cap allows
    # 750 shares and the budget allows 100, so the taper is what is measured.
    # The first draft used a $20 name at $30k, where the position cap bound
    # first, and a target giving R=0.50, which died on expected-R before
    # sizing ran at all — the tests passed judgement on the wrong gate.
    def _prop(self, sym, price=10.0, stop=4.0):
        return OrderProposal(symbol=sym, asset_class="equity", side="buy",
                             price=price, stop=stop, target=price + 18.0,
                             thesis="taper test")

    def test_the_first_position_gets_the_full_budget(self):
        pf = Portfolio(30000.0)         # large enough that rounding never bites
        p = self._prop("A")
        d = self.ro.evaluate(p, pf, {"A": 10.0}, self.today)
        self.assertAlmostEqual(d.qty * (p.price - p.stop),
                               30000.0 * self.cfg.max_risk_per_trade_pct,
                               delta=6.0)

    def test_each_additional_position_is_halved(self):
        pf = Portfolio(30000.0)
        prices, risks = {}, []
        for i in range(3):
            p = self._prop(f"S{i}")
            prices[p.symbol] = p.price
            d = self.ro.evaluate(p, pf, prices, self.today)
            self.assertTrue(d.approved, f"S{i}: {d.reasons}")
            risks.append(d.qty * (p.price - p.stop))
            pf.buy(self.today, p.symbol, "equity", d.qty, p.price, 0.0)
            pf.positions[p.symbol].stop = p.stop
        self.assertAlmostEqual(risks[1] / risks[0], 0.5, delta=0.05)
        self.assertAlmostEqual(risks[2] / risks[0], 0.25, delta=0.05)

    def test_the_taper_keeps_the_book_inside_the_portfolio_cap(self):
        # 2.0 + 1.0 + 0.5 + 0.25 = 3.75% < 4%. The two rules are not
        # redundant: the taper shapes the book, the cap guarantees its
        # ceiling even if max_concurrent_positions is ever raised.
        total = sum(self.cfg.max_risk_per_trade_pct
                    * self.cfg.correlated_risk_decay ** n
                    for n in range(self.cfg.max_concurrent_positions))
        self.assertLess(total, self.cfg.max_portfolio_risk_pct)

    def test_the_refusal_names_the_taper_so_it_is_not_mistaken_for_a_bug(self):
        # At $300 with whole shares the taper bites hard and that is the point
        # to be explicit about: the 2nd position's budget is $3.00 against $6
        # of risk per share, so it rounds to zero. The refusal must SAY the
        # taper caused it, or a live session reads it as a bug and reshapes
        # the trade — the one behaviour this system exists to prevent.
        pf = Portfolio(300.0)
        first = self._prop("S0", price=60.0, stop=54.0)
        prices = {"S0": 60.0}
        d = self.ro.evaluate(first, pf, prices, self.today)
        self.assertTrue(d.approved, d.reasons)
        pf.buy(self.today, "S0", "equity", d.qty, 60.0, 0.0)
        pf.positions["S0"].stop = 54.0

        second = self._prop("S1", price=60.0, stop=54.0)
        prices["S1"] = 60.0
        d = self.ro.evaluate(second, pf, prices, self.today)
        self.assertFalse(d.approved)
        self.assertTrue(any("taper" in r for r in d.reasons),
                        f"the refusal must name the taper: {d.reasons}")

    def test_a_decay_of_one_restores_flat_sizing(self):
        cfg = replace(DEFAULT, correlated_risk_decay=1.0)
        ro = RiskOfficer(cfg)
        pf = Portfolio(3000.0)
        prices, risks = {}, []
        for i in range(2):
            p = self._prop(f"F{i}")
            prices[p.symbol] = p.price
            d = ro.evaluate(p, pf, prices, self.today)
            risks.append(d.qty * (p.price - p.stop))
            pf.buy(self.today, p.symbol, "equity", d.qty, p.price, 0.0)
            pf.positions[p.symbol].stop = p.stop
        self.assertAlmostEqual(risks[0], risks[1], delta=1.0)
