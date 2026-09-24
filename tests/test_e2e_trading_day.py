"""End-to-end: a whole trading day through the real commands.

The unit tests check pieces. Every HIGH-severity defect this project has found
lived at a SEAM between pieces that were each correct:

  T-12  the taper and the book cap read their input from a portfolio that
        paper_session never updated, so both were inert in production while
        every engine-level test passed.
  B-15  paper_session recorded a fill only if it arrived within 30 seconds,
        and the reconciliation that was supposed to catch the rest was never
        written. No unit test could see it; both halves were fine alone.
  M-16  cancel_unfilled_entries lived only in `close`, after the auction.

So these drive `cmd_open`, `cmd_preclose` and `cmd_close` as a session does —
against a fake broker whose state actually changes underneath them — and assert
the things a session would act on.
"""
import argparse
import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.trading_day as td
from tools import state

DAY = dt.date(2026, 9, 24)


class FakeBroker:
    """A broker with state that moves, because that is where the bugs are."""

    def __init__(self, cash=300.0, equity=300.0):
        self.cash, self.equity = cash, equity
        self._positions, self._fills, self._stops = [], [], {}
        # Stops keyed by ORDER, kept forever. In production stop_of_order()
        # reads the bracket's legs, which survive as canceled orders carrying
        # their stop_price after the position closes — so a round trip can
        # still compute R. The first draft of this fake popped the stop when
        # the position closed and made R unmeasurable, which is a property of
        # the fake and not of the system.
        self._order_stops = {}
        self.cancelled = []
        self.raise_on_cancel = False

    # --- what the spine reads
    def account(self):
        return {"equity": self.equity, "cash": self.cash,
                "buying_power": self.cash, "daytrade_count": 0,
                "pattern_day_trader": False, "trading_blocked": False, "raw": {}}

    def positions(self):
        return list(self._positions)

    def positions_without_stops(self):
        return [p["symbol"] for p in self._positions
                if p["symbol"] not in self._stops]

    def resting_stops(self):
        return dict(self._stops)

    def fills_since(self, after):
        return list(self._fills)

    def stop_of_order(self, oid):
        return self._order_stops.get(oid)

    def cancel_unfilled_entries(self):
        if self.raise_on_cancel:
            raise RuntimeError("broker refused the cancel")
        return list(self.cancelled)

    # --- what the test does to it
    # Fills are stamped NOW, not at a hardcoded hour. expected_cash counts
    # only fills AFTER the cash anchor — correctly, because a fill that
    # predates the anchor is already inside the anchored cash figure and
    # counting it again would double-count. The first draft of this fixture
    # hardcoded 14:00Z against an anchor set at the real clock, so every
    # recovered fill looked pre-anchor and the day halted. The exclusion was
    # right; the fixture was not.
    @staticmethod
    def _now():
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def fill_buy(self, symbol, qty, price, stop, at=None):
        at = at or self._now()
        self.cash -= qty * price
        self.equity = self.cash + qty * price
        self._positions.append({"symbol": symbol, "qty": qty,
                                "avg_price": price, "market_value": qty * price,
                                "unrealized_pl": 0.0})
        self._stops[symbol] = stop
        self._order_stops[symbol] = stop
        self._fills.append({"activity_id": f"buy-{symbol}", "order_id": symbol,
                            "symbol": symbol, "side": "buy", "qty": qty,
                            "price": price, "at": at})

    def fill_sell(self, symbol, qty, price, at=None):
        at = at or self._now()
        self.cash += qty * price
        self.equity = self.cash
        self._positions = [p for p in self._positions if p["symbol"] != symbol]
        self._stops.pop(symbol, None)
        self._fills.append({"activity_id": f"sell-{symbol}", "order_id": symbol,
                            "symbol": symbol, "side": "sell", "qty": qty,
                            "price": price, "at": at})


class _Day(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for p in (mock.patch.object(state, "STATE", self.tmp),
                  mock.patch.object(state, "LEDGER", self.tmp / "ledger.json"),
                  mock.patch.object(state, "FILLS", self.tmp / "fills.jsonl"),
                  mock.patch.object(td, "REPORTS", self.tmp / "reports"),
                  mock.patch.object(td, "trading_date", lambda when=None:
                                    DAY if when is None else when.date())):
            p.start(); self.addCleanup(p.stop)
        state.save(dict(state.EMPTY))
        self.broker = FakeBroker()

    def _cmd(self, fn, offline=False):
        buf = io.StringIO()
        with mock.patch.object(td, "get_broker", lambda o: self.broker), \
             contextlib.redirect_stdout(buf):
            rc = fn(argparse.Namespace(offline=offline))
        return rc, buf.getvalue()


class TestAQuietDay(_Day):
    def test_open_then_close_with_no_activity(self):
        rc, out = self._cmd(td.cmd_open)
        self.assertEqual(rc, 0, out)
        self.assertIn("NORMAL", out)
        rc, out = self._cmd(td.cmd_close)
        self.assertEqual(rc, 0, out)

    def test_open_is_idempotent_across_management_firings(self):
        # `open` runs at every firing; it must not re-anchor the daily halt
        # baseline, or a day that is -3% by noon can never reach -4%.
        self._cmd(td.cmd_open)
        first = state.load()["day_start_equity"]
        self.broker.equity = 291.0
        self._cmd(td.cmd_open)
        self.assertEqual(state.load()["day_start_equity"], first)


class TestAFullRoundTripThroughTheSpine(_Day):
    """The T-12/B-15 shape: the broker moves, and the spine must notice."""

    def test_a_fill_the_session_never_recorded_is_recovered_and_reconciles(self):
        self._cmd(td.cmd_open)
        # A limit order fills six minutes later — past FILL_WAIT_SECONDS — so
        # paper_session wrote nothing. This is exactly B-15.
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        rc, out = self._cmd(td.cmd_open)
        self.assertEqual(rc, 0, out)
        self.assertIn("POSTED BUY", out)
        rows = [f for f in state.read_fills() if not f.get("dry_run")]
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["price"], 58.47)
        self.assertAlmostEqual(rows[0]["stop"], 55.80)   # or R is unmeasurable
        self.assertNotIn("CASH DRIFT", out, "the fill must explain the cash")

    def test_the_round_trip_produces_a_measurable_R(self):
        self._cmd(td.cmd_open)
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        self.broker.fill_sell("DT", 1, 58.10)
        self._cmd(td.cmd_open)
        from tools.review import closed_trades
        trades = closed_trades(state.read_fills())
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["pnl"], -0.37, places=2)
        self.assertAlmostEqual(trades[0]["R"], -0.1386, places=3)

    def test_a_fill_is_never_posted_twice_across_repeated_firings(self):
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        for _ in range(3):
            self._cmd(td.cmd_open)
        self.assertEqual(
            len([f for f in state.read_fills() if not f.get("dry_run")]), 1)

    def test_an_unexplained_cash_move_still_halts(self):
        # The recovery must not become a blanket excuse for any discrepancy.
        self._cmd(td.cmd_open)
        self.broker.cash -= 25.0          # no fill, no explanation
        self.broker.equity -= 25.0
        rc, out = self._cmd(td.cmd_open)
        self.assertIn("CASH DRIFT", out)
        self.assertEqual(rc, 1, "an unexplained drift must stop the day")


class TestPreCloseProtectsTheOvernightBook(_Day):
    def test_preclose_passes_a_protected_position(self):
        self._cmd(td.cmd_open)
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        rc, out = self._cmd(td.cmd_preclose)
        self.assertEqual(rc, 0, out)
        self.assertIn("live stop", out)

    def test_preclose_FAILS_an_unprotected_position(self):
        self._cmd(td.cmd_open)
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        del self.broker._stops["DT"]              # the stop vanished
        rc, out = self._cmd(td.cmd_preclose)
        self.assertEqual(rc, 1)
        self.assertIn("UNPROTECTED", out)

    def test_a_broker_that_refuses_to_cancel_fails_loudly(self):
        self._cmd(td.cmd_open)
        self.broker.raise_on_cancel = True
        rc, out = self._cmd(td.cmd_preclose)
        self.assertEqual(rc, 1)
        self.assertIn("could not cancel", out)

    def test_preclose_clears_the_working_order_book(self):
        led = state.load(); led["working_orders"] = [{"symbol": "X"}]
        state.save(led)
        self._cmd(td.cmd_preclose)
        self.assertEqual(state.load()["working_orders"], [])


class TestCloseReportsWhatAHumanMustAct(_Day):
    def test_an_unprotected_carry_is_escalated(self):
        self._cmd(td.cmd_open)
        self.broker.fill_buy("DT", 1, 58.47, stop=55.80)
        del self.broker._stops["DT"]
        _, out = self._cmd(td.cmd_close)
        self.assertIn("Escalate", out)
        self.assertIn("unprotected", out.lower())

    def test_a_clean_day_escalates_nothing(self):
        self._cmd(td.cmd_open)
        _, out = self._cmd(td.cmd_close)
        self.assertIn("nothing", out.lower())

    def test_the_drift_figure_is_reported_even_when_zero(self):
        # A silent control is indistinguishable from one that did not run.
        self._cmd(td.cmd_open)
        _, out = self._cmd(td.cmd_close)
        self.assertIn("drift", out.lower())
