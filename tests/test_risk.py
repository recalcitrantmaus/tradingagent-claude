"""These tests are the constitution's teeth. If one fails, the agent does not
trade until a human has looked at why.
"""
import datetime as dt
import sys
from pathlib import Path
import unittest

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
        pf, ro = fresh()
        ro.state = State.LOCKED
        d = ro.evaluate(equity_order(side="sell"), pf, {"TEC": 50.0}, D)
        self.assertTrue(d.approved)


class TestOptionsGate(unittest.TestCase):
    def opt(self, **kw):
        base = dict(symbol="TEC_C", asset_class="option", side="buy",
                    price=2.00, stop=1.20, multiplier=100, dte=30,
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
        d = ro.evaluate(self.opt(dte=0), pf, {}, D)
        self.assertFalse(d.approved)

    def test_first_15_minutes_rejected(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
        d = ro.evaluate(self.opt(minutes_since_open=5), pf, {}, D)
        self.assertFalse(d.approved)
        self.assertIn("observe", d.reasons[0])

    def test_undefined_risk_rejected(self):
        cfg = replace(DEFAULT, starting_equity=5000.0)
        pf, ro = fresh(cfg)
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
