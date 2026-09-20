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


# ---------------------------------------------------------------------------
# Cash drift. Equity moves every second for legitimate reasons; cash only
# moves when something happened. On 2026-09-18 the broker went 300.00 ->
# 299.99 with no position change and every control reported clean.
# ---------------------------------------------------------------------------
from unittest import mock
from tools.trading_day import (anchor_cash, cash_effect, expected_cash,
                               DRIFT_HALT_ABS)
import tools.trading_day as td


def _fills(*rows):
    return mock.patch.object(td.state, "read_fills", lambda: list(rows))


def fill(side="buy", qty=2, price=10.0, ts="2026-09-18T15:00:00+00:00", **kw):
    return {"side": side, "qty": qty, "price": price, "ts": ts,
            "fees": 0.0, "multiplier": 1, **kw}


class TestCashDrift(unittest.TestCase):
    def base(self, **kw):
        led = {"positions": {}, "cash": 300.0, "broker_cash": 300.0,
               "broker_cash_at": "2026-09-18T20:00:00+00:00"}
        led.update(kw)
        return led

    def test_no_anchor_is_not_a_failure_but_says_so(self):
        with _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=250.0),
                                        {"positions": {}, "cash": 300.0})
        self.assertTrue(ok)
        self.assertTrue(any("no cash anchor yet" in n for n in notes))
        self.assertIsNone(snap["cash_drift"])

    def test_matching_cash_with_no_fills_is_clean(self):
        with _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=300.0), self.base())
        self.assertTrue(ok)
        self.assertFalse(any("CASH DRIFT" in n for n in notes))
        self.assertAlmostEqual(snap["cash_drift"], 0.0)

    def test_the_one_cent_that_started_this_is_caught(self):
        # The exact 2026-09-18 case: a probe round trip, no position change,
        # no recorded fill, and every control previously said "clean".
        with _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=299.99), self.base())
        self.assertTrue(any("CASH DRIFT" in n for n in notes))
        self.assertAlmostEqual(snap["cash_drift"], -0.01)
        self.assertTrue(ok)          # noted, but a cent does not stop the day

    def test_drift_explained_by_a_recorded_fill_is_clean(self):
        # bought 2 @ 10.00 after the anchor -> cash should be 280.00
        with _fills(fill(side="buy", qty=2, price=10.0,
                         ts="2026-09-18T21:00:00+00:00")):
            ok, notes, snap = reconcile(FakeBroker(cash=280.0), self.base())
        self.assertTrue(ok)
        self.assertFalse(any("CASH DRIFT" in n for n in notes))
        self.assertAlmostEqual(snap["cash_drift"], 0.0)

    def test_a_fill_recorded_BEFORE_the_anchor_is_not_double_counted(self):
        with _fills(fill(ts="2026-09-18T19:00:00+00:00")):    # before anchor
            ok, notes, snap = reconcile(FakeBroker(cash=300.0), self.base())
        self.assertAlmostEqual(snap["cash_drift"], 0.0)

    def test_dry_run_fills_do_not_move_the_expectation(self):
        with _fills(fill(ts="2026-09-18T21:00:00+00:00", dry_run=True)):
            ok, notes, snap = reconcile(FakeBroker(cash=300.0), self.base())
        self.assertAlmostEqual(snap["cash_drift"], 0.0)

    def test_material_drift_stops_the_day(self):
        with _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=250.0), self.base())
        self.assertFalse(ok)
        self.assertTrue(any("DO NOT TRADE" in n for n in notes))

    def test_the_halt_threshold_scales_with_equity(self):
        # 0.5% of 5000 = 25, so a $10 drift notes but does not halt
        with _fills():
            ok, notes, snap = reconcile(
                FakeBroker(cash=290.0, equity=5000.0),
                self.base(broker_cash=300.0))
        self.assertTrue(ok)
        self.assertTrue(any("CASH DRIFT" in n for n in notes))

    def test_a_sell_returns_cash(self):
        self.assertAlmostEqual(cash_effect(fill(side="sell", qty=3, price=4.0)),
                               +12.0)
        self.assertAlmostEqual(cash_effect(fill(side="buy", qty=3, price=4.0)),
                               -12.0)

    def test_fees_are_paid_in_both_directions(self):
        self.assertAlmostEqual(
            cash_effect(fill(side="sell", qty=1, price=10.0, fees=0.5)), 9.5)
        self.assertAlmostEqual(
            cash_effect(fill(side="buy", qty=1, price=10.0, fees=0.5)), -10.5)


class TestCashAnchor(unittest.TestCase):
    def test_anchoring_records_the_observation_and_its_time(self):
        led = {}
        anchor_cash(led, {"cash": 287.5, "equity": 301.2, "cash_drift": -0.01},
                    when="2026-09-21T20:05:00+00:00")
        self.assertEqual(led["broker_cash"], 287.5)
        self.assertEqual(led["broker_equity"], 301.2)
        self.assertEqual(led["broker_cash_at"], "2026-09-21T20:05:00+00:00")
        self.assertEqual(led["cash"], 287.5)      # legacy field kept honest
        self.assertEqual(led["reconcile_drift"][-1]["drift"], -0.01)

    def test_drift_history_is_bounded(self):
        led = {}
        for i in range(120):
            anchor_cash(led, {"cash": 300.0, "equity": 300.0, "cash_drift": 0.0},
                        when=f"2026-01-01T00:{i:02d}:00+00:00")
        self.assertEqual(len(led["reconcile_drift"]), 60)

    def test_offline_reports_what_was_last_OBSERVED_not_a_stored_guess(self):
        ok, notes, snap = reconcile(None, {
            "positions": {}, "cash": 300.0, "equity_curve": [],
            "broker_cash": 287.5, "broker_cash_at": "2026-09-21T20:05:00+00:00"})
        self.assertTrue(ok)
        self.assertTrue(any("287.50" in n and "2026-09-21" in n for n in notes))
        self.assertEqual(snap["cash"], 287.5)     # not the stale 300.0
