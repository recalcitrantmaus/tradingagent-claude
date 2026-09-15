"""The daily spine must fail loudly. These pin the ways it is allowed to fail."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.trading_day import reconcile, build_engine, prices_of

TODAY = dt.date(2026, 9, 15)


class FakeBroker:
    def __init__(self, positions=None, unprotected=None, blocked=False,
                 equity=300.0, cash=300.0):
        self._p = positions or []
        self._u = unprotected or []
        self._blocked = blocked
        self._eq, self._cash = equity, cash

    def account(self):
        return {"equity": self._eq, "cash": self._cash, "buying_power": self._cash,
                "daytrade_count": 0, "pattern_day_trader": False,
                "trading_blocked": self._blocked}

    def positions(self):
        return self._p

    def positions_without_stops(self):
        return self._u


def pos(sym, qty=5, avg=10.0, mv=None, pl=0.0):
    return {"symbol": sym, "qty": qty, "avg_price": avg,
            "market_value": mv if mv is not None else qty * avg,
            "unrealized_pl": pl}


class TestReconciliation(unittest.TestCase):
    def test_clean_state_reconciles(self):
        ledger = {"positions": {"F": {}}, "cash": 200.0}
        ok, notes, snap = reconcile(FakeBroker(positions=[pos("F")]), ledger)
        self.assertTrue(ok)
        self.assertEqual(snap["equity"], 300.0)

    def test_position_at_broker_but_not_in_ledger_fails(self):
        ok, notes, _ = reconcile(FakeBroker(positions=[pos("F")]),
                                 {"positions": {}, "cash": 200.0})
        self.assertFalse(ok)
        self.assertTrue(any("NOT in ledger" in n for n in notes))

    def test_position_in_ledger_but_not_at_broker_fails(self):
        ok, notes, _ = reconcile(FakeBroker(positions=[]),
                                 {"positions": {"F": {}}, "cash": 300.0})
        self.assertFalse(ok)
        self.assertTrue(any("NOT at broker" in n for n in notes))

    def test_trading_blocked_fails(self):
        ok, notes, _ = reconcile(FakeBroker(blocked=True),
                                 {"positions": {}, "cash": 300.0})
        self.assertFalse(ok)
        self.assertTrue(any("trading_blocked" in n for n in notes))

    def test_unprotected_position_is_reported(self):
        ok, notes, snap = reconcile(
            FakeBroker(positions=[pos("F")], unprotected=["F"]),
            {"positions": {"F": {}}, "cash": 200.0})
        self.assertTrue(any("NO resting stop" in n for n in notes))
        self.assertEqual(snap["unprotected"], ["F"])

    def test_offline_never_claims_broker_truth(self):
        ok, notes, _ = reconcile(None, {"positions": {}, "cash": 300.0,
                                        "equity_curve": []})
        self.assertTrue(ok)
        self.assertTrue(any("OFFLINE" in n for n in notes))


class TestEngineRebuild(unittest.TestCase):
    """Engine state is rebuilt from the broker, never trusted from the ledger."""

    def test_positions_and_cash_come_from_the_broker_not_the_ledger(self):
        # The ledger claims $999 of cash; the broker says $100. The broker wins.
        _, _, snap = reconcile(
            FakeBroker(positions=[pos("F", qty=7, avg=11.0)], cash=100.0),
            {"positions": {"F": {}}, "cash": 999.0})
        pf, _ = build_engine(snap, {"starting_equity": 300.0, "cash": 999.0}, TODAY)
        self.assertEqual(pf.positions["F"].qty, 7)
        self.assertEqual(pf.cash, 100.0)

    def test_peak_equity_never_regresses(self):
        _, _, snap = reconcile(FakeBroker(equity=250.0, cash=250.0),
                               {"positions": {}, "cash": 250.0})
        pf, _ = build_engine(snap, {"peak_equity": 400.0}, TODAY)
        self.assertEqual(pf.peak_equity, 400.0)
        self.assertAlmostEqual(pf.drawdown(prices_of(snap)), 0.375)

    def test_track_record_starts_disqualifying(self):
        _, _, snap = reconcile(FakeBroker(), {"positions": {}, "cash": 300.0})
        _, ro = build_engine(snap, {}, TODAY)
        self.assertEqual(ro.closed_trades, 0)
        self.assertEqual(ro.expectancy_R, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
