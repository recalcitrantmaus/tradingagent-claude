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


# ---------------------------------------------------------------------------
# The halt baselines must be anchored to the CALENDAR, not to the call.
# `trading_day open` runs at every management firing — midday and pre-close as
# well as the open — and it used to re-anchor day_start_equity every time.
# ---------------------------------------------------------------------------
import contextlib
import io
import argparse



def _on(day=dt.date(2026, 9, 21)):
    """Pin the TRADING day (T-9).

    The seam moved when the trading day stopped being `dt.date.today()` — the
    host's local date — and became an ET calendar date derived from the
    instant. Patching `dt.date` no longer reaches it, which is the point:
    "which session is this" is now one named decision instead of a property
    of the machine the container happens to run on.
    """
    real = td.trading_date
    return mock.patch.object(
        td, "trading_date",
        lambda when=None: day if when is None else real(when))


def _run_open(ledger, equity, today, monkey, cash=300.0, day=None):
    """Invoke cmd_open against a fake broker, returning the mutated ledger.

    Cash is held FIXED while equity moves, because that is what a losing day
    with an open position actually looks like: unrealized P&L moves equity and
    leaves cash alone. An earlier version of this helper moved both, which
    tripped the cash-drift check and made cmd_open return before it reached
    the anchor logic — so the test passed while testing nothing.
    """
    saved = {}
    with mock.patch.object(td.state, "load", lambda: ledger), \
         mock.patch.object(td.state, "save", lambda l: saved.update(l)), \
         mock.patch.object(td.state, "read_fills", lambda: []), \
         mock.patch.object(td, "get_broker",
                           lambda offline: FakeBroker(equity=equity, cash=cash)), \
         mock.patch.object(td.dt, "date", monkey), \
         _on(day or monkey.today()):
        rc = td.cmd_open(argparse.Namespace(offline=False))
    assert rc == 0, f"cmd_open returned {rc}; it never reached the anchors"
    return ledger


class _FixedDate(dt.date):
    """dt.date with today() pinned, so cmd_open sees the day we mean."""
    _today = dt.date(2026, 9, 21)

    @classmethod
    def today(cls):
        return cls._today



class TestHaltBaselinesAnchorToTheCalendar(unittest.TestCase):
    def setUp(self):
        _FixedDate._today = dt.date(2026, 9, 21)      # a Monday

    def test_a_second_open_on_the_same_day_does_not_move_the_daily_anchor(self):
        """The -4% breaker must measure the whole day.

        A day that is -3% by noon used to re-anchor at noon, so a further -3%
        read as -3% and the halt could never fire.
        """
        led = dict(positions={}, cash=300.0)
        _run_open(led, 300.0, None, _FixedDate)          # 09:45, flat
        self.assertEqual(led["day_start_equity"], 300.0)

        _run_open(led, 291.0, None, _FixedDate)          # 12:00, -3%
        self.assertEqual(led["day_start_equity"], 300.0,
                         "midday re-anchored the daily halt baseline")

        _run_open(led, 282.0, None, _FixedDate)          # 15:30, -6% on the day
        self.assertEqual(led["day_start_equity"], 300.0)

    def test_a_new_day_does_re_anchor(self):
        led = dict(positions={}, cash=300.0)
        _run_open(led, 300.0, None, _FixedDate)
        _FixedDate._today = dt.date(2026, 9, 22)         # Tuesday
        _run_open(led, 291.0, None, _FixedDate)
        self.assertEqual(led["day_start_equity"], 291.0)
        self.assertEqual(led["day_start_key"], "2026-09-22")

    def test_monday_does_not_re_anchor_the_week_on_every_run(self):
        led = dict(positions={}, cash=300.0)
        _run_open(led, 300.0, None, _FixedDate)
        _run_open(led, 276.0, None, _FixedDate)          # -8% intraday Monday
        self.assertEqual(led["week_start_equity"], 300.0,
                         "the weekly halt baseline walked downhill")

    def test_a_holiday_monday_still_anchors_the_week_on_tuesday(self):
        """`weekday() == 0` meant a week whose Monday never ran kept the
        PREVIOUS week's anchor, so the -8% breaker measured the wrong week."""
        led = dict(positions={}, cash=300.0,
                   week_start_equity=400.0, week_start_key="2026-W38")
        _FixedDate._today = dt.date(2026, 9, 22)         # Tue of W39
        _run_open(led, 300.0, None, _FixedDate)
        self.assertEqual(led["week_start_equity"], 300.0)
        self.assertEqual(led["week_start_key"], "2026-W39")

    def test_the_risk_officer_gets_the_anchor_not_this_firing(self):
        # The breaker reads ro.day_start_equity; if start_day() overwrote it
        # with the current equity the whole fix would be cosmetic.
        led = dict(positions={}, cash=300.0)
        _run_open(led, 300.0, None, _FixedDate)
        led2 = dict(led)
        with mock.patch.object(td.state, "load", lambda: led2), \
             mock.patch.object(td.state, "save", lambda l: None), \
             mock.patch.object(td.state, "read_fills", lambda: []), \
             mock.patch.object(td, "get_broker",
                               lambda offline: FakeBroker(equity=287.0, cash=287.0)), \
             mock.patch.object(td.dt, "date", _FixedDate):
            snap = {"equity": 287.0, "cash": 287.0, "positions": [],
                    "unprotected": [], "daytrades": 0}
            _, ro = td.build_engine(snap, led2, _FixedDate.today())
            ro.start_day(_FixedDate.today(), snap["equity"])
            ro.day_start_equity = led2["day_start_equity"]
        self.assertEqual(ro.day_start_equity, 300.0)


class TestCumulativeDrift(unittest.TestCase):
    """Each reading is an increment since the last anchor, so a day's readings
    sum. trading_day open runs at every management firing, so three separate
    sub-threshold surprises are three small notes and one material total.
    """

    def led(self, *history, cash=300.0):
        return {"positions": {}, "cash": cash, "broker_cash": cash,
                "broker_cash_at": "2026-09-21T13:45:00+00:00",
                "reconcile_drift": list(history)}

    def hist(self, drift, at="2026-09-21T16:00:00+00:00"):
        return {"at": at, "drift": drift, "broker_cash": 300.0}

    def test_todays_readings_sum_and_yesterdays_do_not(self):
        led = self.led(self.hist(-0.40),
                       self.hist(-0.40, at="2026-09-21T19:30:00+00:00"),
                       self.hist(-9.00, at="2026-09-18T20:00:00+00:00"))
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            _, notes, snap = reconcile(FakeBroker(cash=299.60), led)
        # -0.40 now, -0.80 already today; Friday's -9.00 is not today's problem
        self.assertAlmostEqual(snap["cash_drift"], -0.40)
        self.assertAlmostEqual(snap["cash_drift_today"], -1.20)
        self.assertEqual(snap["drift_readings_today"], 3)
        self.assertTrue(any("CUMULATIVE DRIFT TODAY" in n for n in notes))

    def test_three_small_drifts_halt_the_day_together(self):
        """None of these exceeds the threshold alone; together they do.

        The threshold at this account size is max($1.00, 0.5% of equity) =
        $1.50, NOT the $1.00 floor — the percentage term dominates above $200
        of equity. An earlier version of this test used three 40c drifts,
        totalling $1.20, and failed because the code was right.
        """
        led = self.led(self.hist(-0.60),
                       self.hist(-0.60, at="2026-09-21T19:30:00+00:00"))
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=299.40), led)
        self.assertAlmostEqual(snap["cash_drift"], -0.60)      # each is small
        self.assertAlmostEqual(snap["cash_drift_today"], -1.80)  # together, not
        self.assertFalse(ok)
        self.assertTrue(any("cumulative drift" in n and "DO NOT TRADE" in n
                            for n in notes))

    def test_a_cumulative_total_just_under_the_threshold_does_not_halt(self):
        # the boundary matters: $1.20 against a $1.497 threshold stays open,
        # reported but not halting. Detection is tight, response is tiered.
        led = self.led(self.hist(-0.40),
                       self.hist(-0.40, at="2026-09-21T19:30:00+00:00"))
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=299.60), led)
        self.assertTrue(ok)
        self.assertAlmostEqual(snap["cash_drift_today"], -1.20)
        self.assertTrue(any("CUMULATIVE DRIFT TODAY" in n for n in notes))

    def test_the_halt_threshold_is_the_percentage_not_the_floor_at_this_size(self):
        # Pinned because it is counter-intuitive at $300 and I got it wrong
        # writing these tests: 0.5% of equity passes $1.00 at $200 of equity,
        # so the floor is never the binding term for this account.
        self.assertGreater(td.DRIFT_HALT_PCT * 300.0, td.DRIFT_HALT_ABS)

    def test_a_single_clean_reading_after_a_clean_day_stays_clean(self):
        led = self.led(self.hist(0.0))
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=300.0), led)
        self.assertTrue(ok)
        self.assertAlmostEqual(snap["cash_drift_today"], 0.0)
        self.assertFalse(any("CUMULATIVE" in n for n in notes))

    def test_offsetting_drifts_do_not_hide_each_other_from_the_reader(self):
        # +1.00 then -1.00 nets zero, which is the honest CUMULATIVE answer,
        # but each reading was reported when it happened and both sit in the
        # history. The net is what the halt acts on; the notes carry the rest.
        led = self.led(self.hist(+1.00))
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            ok, notes, snap = reconcile(FakeBroker(cash=299.00), led)
        self.assertAlmostEqual(snap["cash_drift"], -1.00)
        self.assertAlmostEqual(snap["cash_drift_today"], 0.0)
        self.assertTrue(any("CASH DRIFT -1.0000" in n for n in notes))

    def test_the_first_reading_of_the_day_reports_itself_as_the_total(self):
        with _on(), mock.patch.object(td.dt, "date", _FixedDate), _fills():
            _, notes, snap = reconcile(FakeBroker(cash=299.99), self.led())
        self.assertAlmostEqual(snap["cash_drift_today"], -0.01)
        self.assertEqual(snap["drift_readings_today"], 1)
        self.assertFalse(any("CUMULATIVE" in n for n in notes))


class TestPrecloseClosesTheEntryBookBeforeTheBell(unittest.TestCase):
    """M-16. cancel_unfilled_entries() lived only in `close`, which runs after
    16:00 — after the closing cross, the largest print of the day and the
    event most likely to fill a resting limit.
    """

    def run_preclose(self, broker, ledger):
        with mock.patch.object(td.state, "load", lambda: ledger), \
             mock.patch.object(td.state, "save", lambda l: None), \
             mock.patch.object(td.state, "read_fills", lambda: []), \
             mock.patch.object(td, "get_broker", lambda offline: broker), \
             mock.patch.object(td.dt, "date", _FixedDate):
            return td.cmd_preclose(argparse.Namespace(offline=False))

    def test_it_cancels_resting_entries(self):
        cancelled = []

        class B(FakeBroker):
            def cancel_unfilled_entries(self):
                cancelled.append(True)
                return ["ETHA:abc123"]

        rc = self.run_preclose(B(), {"positions": {}, "cash": 300.0})
        self.assertEqual(rc, 0)
        self.assertTrue(cancelled, "preclose did not cancel the entry book")

    def test_it_FAILS_if_cancelling_left_a_position_unprotected(self):
        # The whole point of re-reading after the cancel: if that call took a
        # stop off an open position, find out while the market is still open.
        class B(FakeBroker):
            def cancel_unfilled_entries(self):
                return ["AAA:parent"]
            def positions_without_stops(self):
                return ["AAA"]

        rc = self.run_preclose(B(positions=[pos("AAA")]),
                               {"positions": {"AAA": {}}, "cash": 300.0})
        self.assertEqual(rc, 1, "an unprotected position must stop the session")

    def test_it_clears_working_orders_once_the_book_is_empty(self):
        led = {"positions": {}, "cash": 300.0,
               "working_orders": [{"symbol": "ETHA", "order_id": "abc"}]}

        class B(FakeBroker):
            def cancel_unfilled_entries(self):
                return ["ETHA:abc"]

        self.run_preclose(B(), led)
        self.assertEqual(led["working_orders"], [])

    def test_a_broker_error_stops_the_session_rather_than_passing_quietly(self):
        class B(FakeBroker):
            def cancel_unfilled_entries(self):
                raise RuntimeError("broker unreachable")

        self.assertEqual(self.run_preclose(B(), {"positions": {}, "cash": 300.0}), 1)


class TestTheTradingDayIsAnExchangeDate(unittest.TestCase):
    """T-9. "Today" used to be `dt.date.today()` — the container's local date,
    which is UTC — compared against UTC timestamps by string prefix.

    UTC midnight is 20:00 ET, four hours after the close but on the same
    session's evening, so the drift window opened the previous evening. The
    2026-09-22 close session's four readings included one from Monday 22:32
    ET, and the cumulative figure feeds `drift_halts` — so an evening's drift
    would have counted against the wrong session. Crypto, which the plan
    permits, fills around the clock.

    It was also decided by the HOST: the same code on an ET machine compares
    an ET date against UTC timestamp strings and buckets differently, or
    matches nothing. A check decided by where it runs (M-28's shape).
    """

    def test_an_evening_timestamp_belongs_to_the_session_that_just_ended(self):
        # 2026-09-22T01:00:00Z is 2026-09-21 21:00 ET — Monday evening, after
        # Monday's close. It is MONDAY's trading day, not Tuesday's.
        ts = dt.datetime(2026, 9, 22, 1, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(td.trading_date(ts), dt.date(2026, 9, 21))
        self.assertNotEqual(td.trading_date(ts), ts.date())

    def test_a_session_timestamp_is_its_own_date(self):
        # 14:30Z = 10:30 ET, mid-session.
        ts = dt.datetime(2026, 9, 22, 14, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(td.trading_date(ts), dt.date(2026, 9, 22))

    def test_dst_is_carried_not_hardcoded(self):
        # A fixed -05:00 would put this on the wrong day in summer. 2026-07-01
        # 23:30Z is 19:30 EDT (-04:00), still 07-01; the same instant at a
        # hardcoded -05:00 would read 18:30 and also 07-01, so use the case
        # that actually separates them: 03:30Z in July is 23:30 EDT of the
        # PREVIOUS day, where a -05:00 offset would say 22:30 previous day —
        # same date — but in January 03:30Z is 22:30 EST, also previous day.
        # The real discriminator is the transition weekend itself.
        summer = dt.datetime(2026, 7, 1, 3, 30, tzinfo=dt.timezone.utc)
        winter = dt.datetime(2026, 1, 7, 3, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(td.trading_date(summer), dt.date(2026, 6, 30))
        self.assertEqual(td.trading_date(winter), dt.date(2026, 1, 6))
        # 2026-03-08 is the US DST transition. 06:30Z is 01:30 EST on the 8th.
        spring = dt.datetime(2026, 3, 8, 6, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(td.trading_date(spring), dt.date(2026, 3, 8))

    def test_a_naive_timestamp_is_read_as_utc_not_as_local(self):
        naive = dt.datetime(2026, 9, 22, 1, 0)
        self.assertEqual(td.trading_date(naive), dt.date(2026, 9, 21))

    def test_an_unparseable_timestamp_is_excluded_not_counted_as_today(self):
        # A reading attributed to the wrong session is worse than a missing
        # one, because the halt check believes it.
        led = {"reconcile_drift": [{"at": "not a timestamp", "drift": -99.0},
                                   {"at": None, "drift": -99.0}]}
        total, n = td.drift_today(led, dt.date(2026, 9, 22))
        self.assertEqual((total, n), (0.0, 0))

    def test_the_evening_reading_does_not_join_the_next_days_total(self):
        # The concrete 2026-09-22 case, pinned.
        led = {"reconcile_drift": [
            {"at": "2026-09-22T02:32:52+00:00", "drift": -5.00},   # Mon 22:32 ET
            {"at": "2026-09-22T14:00:00+00:00", "drift": -0.40},   # Tue 10:00 ET
        ]}
        tue, n_tue = td.drift_today(led, dt.date(2026, 9, 22))
        mon, n_mon = td.drift_today(led, dt.date(2026, 9, 21))
        self.assertAlmostEqual(tue, -0.40)
        self.assertEqual(n_tue, 1)
        self.assertAlmostEqual(mon, -5.00)
        self.assertEqual(n_mon, 1)

    def test_the_answer_does_not_depend_on_when_the_suite_runs(self):
        # Yesterday's regression was a suite the environment decided. These
        # are absolute instants, so the mapping is fixed forever.
        for ts, expect in ((dt.datetime(2026, 9, 22, 0, 1, tzinfo=dt.timezone.utc),
                            dt.date(2026, 9, 21)),
                           (dt.datetime(2026, 9, 22, 23, 59, tzinfo=dt.timezone.utc),
                            dt.date(2026, 9, 22))):
            self.assertEqual(td.trading_date(ts), expect)


class TestExitCriteriaDoNotRewardInactivity(unittest.TestCase):
    """T-8. Three of five criteria passed VACUOUSLY on an account that had
    never traded — `all()` over an empty list is True, and "costs below gains"
    carried an explicit `if trades else True`. A flat account printed three
    [ok]s and read three-fifths of the way to Phase 2 exit.

    Same shape as "no protective leg was stripped — vacuously, with no
    position": a check that cannot fail is not evidence. A scorecard that
    cannot tell "passed" from "never ran" rewards doing nothing.
    """

    def _week(self, ledger, fills):
        buf = io.StringIO()
        with mock.patch.object(td.state, "load", lambda: ledger), \
             mock.patch.object(td.state, "read_fills", lambda: fills), \
             contextlib.redirect_stdout(buf):
            rc = td.cmd_week(argparse.Namespace(offline=True))
        return rc, buf.getvalue()

    def test_a_flat_account_scores_zero_not_three_fifths(self):
        led = {"days": [{"equity": 300.0, "risk_state": "NORMAL",
                         "escalations": []} for _ in range(7)],
               "week_start_equity": 300.0}
        rc, out = self._week(led, [])
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("[ok]"), 0,
                         f"a flat account passed a criterion:\n{out}")
        self.assertIn("0/5 met", out)
        self.assertIn("NOT YET MEASURABLE", out)

    def test_an_untested_guardrail_is_unmeasurable_not_passed(self):
        # You cannot breach a rail you never touched, and LOCKED needs a -20%
        # drawdown, which needs losses, which needs trades.
        led = {"days": [{"equity": 300.0, "risk_state": "NORMAL",
                         "escalations": []}], "week_start_equity": 300.0}
        _, out = self._week(led, [])
        for line in out.splitlines():
            if "zero guardrail breaches" in line or "never LOCKED" in line:
                self.assertIn("[--]", line)

    def test_the_trade_count_is_always_measurable_and_can_fail(self):
        led = {"days": [], "week_start_equity": 300.0}
        _, out = self._week(led, [])
        self.assertTrue(any("[XX]" in l and "30+ closed trades" in l
                            for l in out.splitlines()), out)

    def test_exit_still_requires_every_criterion_to_be_measurable_AND_passed(self):
        # The gate must not be satisfiable by an unmeasurable criterion.
        led = {"days": [{"equity": 300.0, "risk_state": "NORMAL",
                         "escalations": []}], "week_start_equity": 300.0}
        rc, _ = self._week(led, [])
        self.assertEqual(rc, 1)
