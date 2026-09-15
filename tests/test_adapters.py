"""Adapter safety: nothing reaches a broker without passing through the gate."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import base
from adapters.base import AdapterError, Authorization, OrderTicket
from adapters.robinhood_mcp import preflight, ticket_to_mcp_args

TODAY = dt.date(2026, 9, 15)


def ticket(**kw):
    d = dict(symbol="F", asset_class="equity", side="buy", qty=5,
             limit_price=11.00, stop_price=10.20, take_profit=13.00)
    d.update(kw)
    return OrderTicket(**d)


class TestAuthorization(unittest.TestCase):
    def test_stale_authorization_is_refused(self):
        a = Authorization("recalcitrantmaus", TODAY - dt.timedelta(days=1), "ok", 500.0)
        ok, why = a.valid_for(TODAY, 100.0)
        self.assertFalse(ok)
        self.assertIn("same-day", why)

    def test_notional_ceiling_is_enforced(self):
        a = Authorization("recalcitrantmaus", TODAY, "ok", 50.0)
        ok, why = a.valid_for(TODAY, 100.0)
        self.assertFalse(ok)
        self.assertIn("ceiling", why)

    def test_same_day_within_ceiling_passes(self):
        a = Authorization("recalcitrantmaus", TODAY, "phase 3 day 1", 500.0)
        ok, _ = a.valid_for(TODAY, 100.0)
        self.assertTrue(ok)


class TestPreflight(unittest.TestCase):
    def good(self, **kw):
        d = dict(risk_state="NORMAL", ledger_reconciled_on=TODAY.isoformat(),
                 positions_without_stops=[], equity=300.0,
                 decision_approved=True, ticket=ticket(), today=TODAY,
                 require_authorization=False)
        d.update(kw)
        return preflight(**d)

    def test_clean_state_passes(self):
        self.assertTrue(self.good().ok)

    def test_halted_account_fails(self):
        self.assertFalse(self.good(risk_state="DAY_HALT").ok)

    def test_unreconciled_ledger_fails(self):
        self.assertFalse(self.good(ledger_reconciled_on=None).ok)

    def test_unprotected_position_fails(self):
        self.assertFalse(self.good(positions_without_stops=["TSLA"]).ok)

    def test_unapproved_decision_fails(self):
        self.assertFalse(self.good(decision_approved=False).ok)

    def test_stop_above_entry_fails(self):
        self.assertFalse(self.good(ticket=ticket(stop_price=12.0)).ok)

    def test_notional_over_equity_fails(self):
        self.assertFalse(self.good(ticket=ticket(qty=1000)).ok)

    def test_missing_authorization_fails_when_required(self):
        original = base.AUTH_FILE
        base.AUTH_FILE = Path("/nonexistent/authorization.json")
        try:
            self.assertFalse(self.good(require_authorization=True).ok)
        finally:
            base.AUTH_FILE = original

    def test_mcp_args_carry_the_stop(self):
        args = ticket_to_mcp_args(ticket())
        self.assertEqual(args["stop_loss_price"], 10.20)
        self.assertEqual(args["order_type"], "limit")


class TestAlpacaGuards(unittest.TestCase):
    def test_missing_keys_refuses_to_construct(self):
        from adapters.alpaca import AlpacaAdapter
        import os
        saved = {k: os.environ.pop(k, None)
                 for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")}
        try:
            with self.assertRaises(AdapterError):
                AlpacaAdapter()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_live_requires_explicit_confirmation(self):
        from adapters.alpaca import AlpacaAdapter
        a = AlpacaAdapter(live=True, key_id="k", secret="s")
        with self.assertRaises(AdapterError):
            a.submit(ticket(), confirm_live=False)

    def test_bars_requests_a_window_and_returns_the_tail(self):
        """A silently short or silently stale series misprices every stop.

        Alpaca returns one bar when `start` is omitted, and truncates from the
        start of the window rather than the end when `limit` is supplied. Both
        read as a normal empty result upstream, so both are pinned here.
        """
        from adapters.alpaca import AlpacaAdapter
        a = AlpacaAdapter(key_id="k", secret="s")
        seen = {}

        def fake_request(method, url, body=None):
            seen["url"] = url
            bars = [{"t": f"2026-0{1 + i // 28}-{1 + i % 28:02d}T04:00:00Z",
                     "o": 1.0, "h": 2.0, "l": 0.5, "c": float(i), "v": 100}
                    for i in range(90)]
            return {"bars": bars, "next_page_token": None}

        a._request = fake_request
        out = a.bars("F", limit=60)

        self.assertIn("start=", seen["url"], "no start: Alpaca returns one bar")
        self.assertEqual(len(out), 60, "should return exactly the tail requested")
        self.assertEqual(out[-1]["close"], 89.0, "tail must be the newest bars")
        self.assertEqual(out[0]["close"], 30.0)

    def test_bars_follows_pagination(self):
        from adapters.alpaca import AlpacaAdapter
        a = AlpacaAdapter(key_id="k", secret="s")
        pages = [
            {"bars": [{"t": "2026-09-01T04:00:00Z", "o": 1, "h": 2, "l": 1,
                       "c": 10, "v": 1}], "next_page_token": "tok"},
            {"bars": [{"t": "2026-09-02T04:00:00Z", "o": 1, "h": 2, "l": 1,
                       "c": 20, "v": 1}], "next_page_token": None},
        ]
        calls = []

        def fake_request(method, url, body=None):
            calls.append(url)
            return pages[len(calls) - 1]

        a._request = fake_request
        out = a.bars("F", limit=10)
        self.assertEqual(len(out), 2)
        self.assertEqual([r["close"] for r in out], [10, 20])
        self.assertIn("page_token=tok", calls[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMarketDataGuards(unittest.TestCase):
    """The cross-check must refuse to paper over a price disagreement."""

    def test_agreeing_prices_pass(self):
        from adapters import marketdata
        original = marketdata.daily_bars
        marketdata.daily_bars = lambda s, rng="5d": [
            type("B", (), {"close": 100.0})()]
        try:
            r = marketdata.cross_check("X", 100.2)
            self.assertTrue(r["agree"])
        finally:
            marketdata.daily_bars = original

    def test_disagreeing_prices_say_stand_down(self):
        from adapters import marketdata
        original = marketdata.daily_bars
        marketdata.daily_bars = lambda s, rng="5d": [
            type("B", (), {"close": 100.0})()]
        try:
            r = marketdata.cross_check("X", 110.0)
            self.assertFalse(r["agree"])
            self.assertIn("do not trade", r["note"])
        finally:
            marketdata.daily_bars = original


class TestLedgerContinuity(unittest.TestCase):
    """A reborn ledger un-trips the circuit breakers, so it must be visible.

    Every Routine firing gets a fresh clone. If the ledger is not committed it
    comes back as EMPTY — risk_state NORMAL, peak_equity at the deposit, no
    halts — which silently clears a halt and resets the peak the drawdown lock
    measures against.
    """

    def _isolate(self):
        import tempfile
        from tools import state
        d = Path(tempfile.mkdtemp())
        saved = (state.STATE, state.LEDGER, state.FILLS)
        state.STATE, state.LEDGER, state.FILLS = d, d / "ledger.json", d / "fills.jsonl"
        return state, saved

    def test_missing_ledger_is_flagged_reborn(self):
        state, saved = self._isolate()
        try:
            self.assertTrue(state.load().get("reborn"),
                            "a ledger built from EMPTY must announce itself")
        finally:
            state.STATE, state.LEDGER, state.FILLS = saved

    def test_existing_ledger_is_not_flagged(self):
        state, saved = self._isolate()
        try:
            state.save({"risk_state": "HALTED_DAY", "peak_equity": 412.0})
            d = state.load()
            self.assertNotIn("reborn", d)
            self.assertEqual(d["risk_state"], "HALTED_DAY")
            self.assertEqual(d["peak_equity"], 412.0)
        finally:
            state.STATE, state.LEDGER, state.FILLS = saved

    def test_state_files_are_tracked_by_git(self):
        """The fix for the reborn ledger is that state/ is committed."""
        ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text()
        for pattern in ("state/ledger.json", "state/fills.jsonl",
                        "state/reports/*", "state/plans/*"):
            self.assertNotIn(f"\n{pattern}", f"\n{ignore}",
                             f"{pattern} must stay tracked or state cannot "
                             f"survive a fresh container")
