"""One test per defect this project has actually shipped and then found.

The unit and e2e suites test behaviour. This file tests HISTORY: every entry
below is a bug that reached the repository, was believed correct at the time,
and would have cost money or credibility. Several were introduced by the fix
for a previous one.

The value of having them in a single file is that the recurring SHAPES become
visible. Four of them appear more than once:

  A  a control reading a value that cannot vary with what it claims to measure
  B  a check that passes vacuously and is therefore trusted for nothing
  C  a datum that is present but means something other than it appears
  D  a control that is correct in isolation and never receives the state that
     makes it bind

Each test names its bug id and its shape. If one goes red, the bug is back.
"""
import datetime as dt
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.trading_day as td
from adapters.alpaca import AlpacaAdapter
from engine.config import DEFAULT
from engine.model_policy import check
from engine.portfolio import Portfolio
from engine.risk import OrderProposal, RiskOfficer
from tools.screen import breakout_now, completed


class TestShapeA_ControlsThatMeasuredTheWrongThing(unittest.TestCase):

    def test_M17_effort_is_read_from_the_harness_not_the_declaration(self):
        # The gate read TRADING_AGENT_EFFORT, an operator declaration set once
        # per environment, while CLAUDE_EFFORT — the harness's measurement —
        # sat unread. On 2026-09-21 they disagreed and the gate cleared an
        # effort the session was not running at.
        with mock.patch.dict("os.environ",
                             {"CLAUDE_EFFORT": "high",
                              "TRADING_AGENT_EFFORT": "xhigh"}, clear=True):
            _, msgs = check("execution", model="claude-opus-5")
        self.assertTrue(any("EFFORT MISMATCH" in m for m in msgs),
                        "a declared/measured disagreement must be loud")

    def test_M22_M26_an_environment_flag_cannot_authorise_a_blocking_task(self):
        # is_attended() read CLAUDE_CODE_SESSION_ATTENDED, set environment-wide,
        # so it was "1" in every session and the gate never once refused.
        with mock.patch.dict("os.environ",
                             {"CLAUDE_EFFORT": "xhigh",
                              "CLAUDE_CODE_SESSION_ATTENDED": "1"}, clear=True):
            ok, _ = check("rule-promotion", model="claude-opus-5")
        self.assertFalse(ok, "an env flag must not clear a blocking gate")

    def test_T9_the_trading_day_is_the_exchanges_not_the_containers(self):
        # "today" was dt.date.today() — UTC in this container — matched against
        # UTC timestamps, so the drift window opened at 20:00 ET the previous
        # evening and a Monday-night reading counted against Tuesday.
        evening = dt.datetime(2026, 9, 22, 1, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(td.trading_date(evening), dt.date(2026, 9, 21))


class TestShapeB_ChecksThatCouldNotFail(unittest.TestCase):

    def test_B20_a_take_profit_is_not_a_stop(self):
        # positions_without_stops marked a symbol protected on
        # order_class in (bracket, oto, oco). A filled bracket surfaces its
        # take-profit first, carrying order_class="bracket" — so a position
        # read as protected with the stop leg gone entirely.
        a = AlpacaAdapter.__new__(AlpacaAdapter)
        a.base = "https://paper-api.alpaca.markets"
        a._request = lambda m, u: [{
            "symbol": "DT", "status": "filled", "order_class": "bracket",
            "legs": [{"type": "limit", "status": "new", "limit_price": "63.81"}]}]
        a.positions = lambda: [{"symbol": "DT", "qty": 1.0, "avg_price": 58.47,
                                "market_value": 58.25, "unrealized_pl": -0.22}]
        self.assertEqual(a.positions_without_stops(), ["DT"])

    def test_the_held_correction_a_real_stop_still_counts_as_protection(self):
        # And the correction that followed: `held` means monitored, not broken.
        # Treating it as unprotected would flag every correct bracket.
        a = AlpacaAdapter.__new__(AlpacaAdapter)
        a.base = "https://paper-api.alpaca.markets"
        a._request = lambda m, u: [{
            "symbol": "DT", "status": "filled", "order_class": "bracket",
            "legs": [{"type": "limit", "status": "new", "limit_price": "63.81"},
                     {"type": "stop", "status": "held", "stop_price": "55.80"}]}]
        a.positions = lambda: [{"symbol": "DT", "qty": 1.0, "avg_price": 58.47,
                                "market_value": 58.25, "unrealized_pl": -0.22}]
        self.assertEqual(a.positions_without_stops(), [])

    def test_T8_a_flat_account_passes_no_exit_criterion(self):
        # Three of five criteria passed vacuously, so an account that had never
        # traded read three-fifths of the way to Phase 2 exit.
        import argparse, contextlib, io
        led = {"days": [{"equity": 300.0, "risk_state": "NORMAL",
                         "escalations": []} for _ in range(7)],
               "week_start_equity": 300.0}
        buf = io.StringIO()
        with mock.patch.object(td.state, "load", lambda: led), \
             mock.patch.object(td.state, "read_fills", lambda: []), \
             contextlib.redirect_stdout(buf):
            rc = td.cmd_week(argparse.Namespace(offline=True))
        out = buf.getvalue()
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("[ok]"), 0, out)


class TestShapeC_DataThatMeantSomethingElse(unittest.TestCase):

    def test_M30_the_breakout_level_comes_from_bars_and_the_price_does_not(self):
        # IEX is one venue at ~3.8% of consolidated volume. It cannot misprice
        # a mean but it misprices an EXTREMUM, which is the only statistic the
        # series is used for. RKLB: IEX 20-day high 70.56, consolidated 71.21,
        # and a trade at 70.76 read as a breakout that had not happened.
        from engine.market import Bar
        def series(high):
            return [Bar(dt.date(2026, 9, 1) + dt.timedelta(days=i),
                        60.0, high if i == 33 else 60.0, 59.0, 60.0, 1e6)
                    for i in range(34)]
        self.assertIsNotNone(breakout_now(series(70.56), 70.76))   # the phantom
        self.assertIsNone(breakout_now(series(71.21), 70.76))      # the truth

    def test_M29_the_current_session_is_not_a_completed_one(self):
        from engine.market import Bar
        today = dt.date(2026, 9, 24)
        bars = [Bar(today - dt.timedelta(days=i), 1, 1, 1, 1, 1)
                for i in range(3)][::-1]
        self.assertTrue(all(b.date < today for b in completed(bars, today)))
        self.assertEqual(len(completed(bars, today)), 2)


class TestShapeD_ControlsThatNeverReceivedTheirState(unittest.TestCase):

    def _full_budget(self, sym):
        return OrderProposal(symbol=sym, asset_class="equity", side="buy",
                             price=60.0, stop=54.0, target=78.0, thesis="t")

    def test_T1_the_book_cannot_carry_more_than_the_daily_halt(self):
        # 4 positions x 2% was 8% of equity at risk simultaneously — twice the
        # daily halt and exactly the weekly one — with nothing capping the sum.
        cfg = replace(DEFAULT, correlated_risk_decay=1.0)
        ro, pf = RiskOfficer(cfg), Portfolio(300.0)
        today, prices, total = dt.date(2026, 9, 24), {}, 0.0
        for i in range(4):
            p = self._full_budget(f"S{i}")
            prices[p.symbol] = p.price
            d = ro.evaluate(p, pf, prices, today)
            if d.approved and d.qty:
                pf.buy(today, p.symbol, "equity", d.qty, p.price, 0.0)
                pf.positions[p.symbol].stop = p.stop
                total += d.qty * (p.price - p.stop)
        self.assertLessEqual(total / 300.0, cfg.max_portfolio_risk_pct + 1e-9)
        self.assertLessEqual(total / 300.0, cfg.daily_loss_halt_pct + 1e-9)

    def test_T1_the_cap_reads_the_portfolio_it_is_actually_given(self):
        # T-12: paper_session called evaluate() in a loop and never mutated the
        # portfolio, so every proposal was gated as position 1 against an empty
        # book and BOTH new controls were inert in production while every
        # engine-level test passed.
        ro = RiskOfficer(DEFAULT)
        today = dt.date(2026, 9, 24)
        empty, loaded = Portfolio(300.0), Portfolio(300.0)
        loaded.buy(today, "X", "equity", 1.0, 60.0, 0.0)
        loaded.positions["X"].stop = 54.0
        p = self._full_budget("Y")
        d_empty = ro.evaluate(p, empty, {"Y": 60.0}, today)
        d_loaded = ro.evaluate(p, loaded, {"Y": 60.0, "X": 60.0}, today)
        self.assertGreater(d_empty.qty or 0, d_loaded.qty or 0,
                           "an occupied book must size smaller than an empty one")

    def test_B15_a_fill_the_session_never_saw_is_still_recorded(self):
        # paper_session recorded a fill only if it arrived within 30 seconds,
        # and the reconciliation its own comment promised was never written.
        class Feed:
            def fills_since(self, after):
                return [{"activity_id": "x", "order_id": "o", "symbol": "DT",
                         "side": "buy", "qty": 1.0, "price": 58.47,
                         "at": "2026-09-23T14:04:57Z"}]
            def stop_of_order(self, oid):
                return 55.80
        written = []
        with mock.patch.object(td.state, "append_fill", written.append), \
             mock.patch.object(td.state, "read_fills", lambda: []):
            notes, explained = td.post_broker_fills(
                Feed(), {"broker_cash_at": "2026-09-23T13:00:00Z"})
        self.assertEqual(len(written), 1)
        self.assertAlmostEqual(written[0]["stop"], 55.80)   # or R is None
        self.assertEqual(explained, {"DT"})
