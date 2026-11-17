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
from adapters.alpaca import AlpacaAdapter

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


class TestNetcheckHonesty(unittest.TestCase):
    """A host that answers is not a host that serves data."""

    def _probe_with(self, exc):
        import urllib.request
        from tools import netcheck
        original = urllib.request.urlopen

        def boom(*a, **kw):
            raise exc
        urllib.request.urlopen = boom
        try:
            return netcheck.probe("example.gov", "/x")
        finally:
            urllib.request.urlopen = original

    def test_403_is_degraded_not_ok(self):
        """www.bls.gov sat green in preflight while returning nothing."""
        import urllib.error
        ok, msg = self._probe_with(
            urllib.error.HTTPError("https://example.gov/x", 403, "Forbidden", {}, None))
        self.assertFalse(ok, "a 403 means reachable, not usable")
        self.assertIn("DEGRADED", msg)

    def test_a_bot_wall_served_as_401_is_degraded(self):
        """reuters.com and marketwatch.com both did exactly this.

        Both were reported "ok — host answered" for weeks because the status
        code was inspected and the body was not. A challenge is a challenge
        whatever number it arrives under.
        """
        import io
        import urllib.error
        body = io.BytesIO(b'<html><head><style>#cmsg{animation: A 1.5s;}</style>')
        ok, msg = self._probe_with(urllib.error.HTTPError(
            "https://example.com/x", 401, "Unauthorized", {}, body))
        self.assertFalse(ok)
        self.assertIn("DEGRADED", msg)
        self.assertIn("challenge", msg)

    def test_401_still_counts_as_reachable(self):
        """Missing a key is a credentials problem, not a closed network."""
        import urllib.error
        import io
        ok, _ = self._probe_with(urllib.error.HTTPError(
            "https://example.gov/x", 401, "Unauthorized", {}, io.BytesIO(b"{}")))
        self.assertTrue(ok)

    def test_user_agent_without_a_contact_names_the_repo_and_no_address(self):
        """SEC and BLS refuse any UA without an address in parentheses.

        The address is the operator's to choose and is never committed, so
        unset must mean no address at all, not a fake one: a dead letterbox
        would get past the WAFs and answer SEC's request for a contact
        dishonestly. netcheck then reports SEC/BLS DEGRADED, which names the
        fix.
        """
        import os
        from tools import netcheck
        saved = os.environ.pop("TRADING_AGENT_CONTACT", None)
        try:
            ua = netcheck.user_agent()
            self.assertNotIn("@", ua)
            self.assertIn(netcheck.REPO_URL, ua)
        finally:
            if saved is not None:
                os.environ["TRADING_AGENT_CONTACT"] = saved

    def test_user_agent_does_not_impersonate_a_browser(self):
        """adapters/marketdata.py used to send Mozilla/5.0.

        Spoofing is both dishonest and ineffective here: a browser UA is
        refused by dol.gov, and Yahoo serves the honest one identically.
        """
        from tools import netcheck
        from adapters import marketdata
        for ua in (netcheck.user_agent(), marketdata.UA):
            self.assertNotIn("Mozilla", ua)
            self.assertIn("tradingagent-claude", ua)

    def test_one_user_agent_across_the_agent(self):
        """Two different UAs is how one source refuses one code path only."""
        from tools import netcheck
        from adapters import marketdata
        self.assertEqual(marketdata.UA, netcheck.user_agent())

    def test_user_agent_carries_the_configured_contact(self):
        import os
        from tools import netcheck
        saved = os.environ.get("TRADING_AGENT_CONTACT")
        os.environ["TRADING_AGENT_CONTACT"] = "someone@example.com"
        try:
            self.assertIn("someone@example.com", netcheck.user_agent())
        finally:
            if saved is None:
                os.environ.pop("TRADING_AGENT_CONTACT", None)
            else:
                os.environ["TRADING_AGENT_CONTACT"] = saved


class TestPreflightDataPrecedence(unittest.TestCase):
    """The fallback must never be able to cancel a trading day."""

    def test_cross_check_failure_does_not_block(self):
        from adapters import marketdata
        from tools import preflight_phase2 as pf
        original = marketdata.cross_check

        def boom(*a, **kw):
            raise AdapterError("HTTP 429")
        marketdata.cross_check = boom
        try:
            check = next(fn for name, fn, _ in pf.CHECKS if name == "live data")
            ok, detail = check()
            self.assertTrue(ok, "a 429 from the keyless fallback is not a stop")
            self.assertIn("cross-check unavailable", detail)
        finally:
            marketdata.cross_check = original

    def test_a_cross_check_disagreement_is_surfaced(self):
        """50bps apart means stand down on that symbol; it must not be silent."""
        from adapters import marketdata
        from tools import preflight_phase2 as pf
        original = marketdata.cross_check
        marketdata.cross_check = lambda *a, **kw: {
            "agree": False, "diff_bps": 250.0}
        try:
            check = next(fn for name, fn, _ in pf.CHECKS if name == "live data")
            _, detail = check()
            self.assertIn("DISAGREES", detail)
        finally:
            marketdata.cross_check = original


class TestFredAdapter(unittest.TestCase):
    """A macro number without its date reads as sourced while being stale."""

    def _stub(self, csv):
        from adapters import fred
        original = fred._fetch
        fred._fetch = lambda sid, timeout=30: csv
        return fred, original

    def test_parses_observations_oldest_first(self):
        fred, original = self._stub(
            "observation_date,ICSA\n2026-09-05,201000\n2026-09-12,196000\n")
        try:
            rows = fred.series("ICSA")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1], (dt.date(2026, 9, 12), 196000.0))
        finally:
            fred._fetch = original

    def test_missing_values_are_dropped_not_zeroed(self):
        """FRED writes an unreported observation as '.'.

        Reading that as 0.0 turns a gap into a reading of zero, which for a
        credit spread or a policy rate is not a small error.
        """
        fred, original = self._stub(
            "observation_date,X\n2026-09-05,2.70\n2026-09-08,.\n2026-09-12,2.75\n")
        try:
            rows = fred.series("X")
            self.assertEqual([v for _, v in rows], [2.70, 2.75])
        finally:
            fred._fetch = original

    def test_an_all_missing_series_raises_rather_than_returning_empty(self):
        fred, original = self._stub("observation_date,X\n2026-09-05,.\n")
        try:
            with self.assertRaises(AdapterError):
                fred.series("X")
        finally:
            fred._fetch = original

    def test_snapshot_reports_staleness(self):
        fred, original = self._stub(
            "observation_date,ICSA\n2020-01-01,100\n")
        try:
            snap = fred.snapshot(["ICSA"])
            self.assertEqual(snap["ICSA"]["as_of"], "2020-01-01")
            self.assertGreater(snap["ICSA"]["stale_days"], 1000)
            self.assertIn("jobless", snap["ICSA"]["name"])
        finally:
            fred._fetch = original


class TestTheStopOutlivesTheSession(unittest.TestCase):
    """Measured against the paper broker on 2026-09-18.

    A bracket's protective legs inherit the parent's time_in_force. Under
    "day" the stop leg is cancelled at 16:00 with the position still open,
    which leaves it naked through the overnight gap. The strategy is a
    multi-day breakout (target = entry + 3*ATR) and PDT allows only 3 day
    trades per 5 days, so carrying overnight is not optional — it is the
    normal case, and it has to be the protected case.
    """

    def test_brackets_default_to_gtc_so_the_stop_survives_the_close(self):
        t = OrderTicket(symbol="F", asset_class="equity", side="buy", qty=1,
                        limit_price=10.0, stop_price=9.4)
        self.assertEqual(t.time_in_force, "gtc")

    def test_cancelling_entries_never_touches_a_live_protective_leg(self):
        from adapters.alpaca import AlpacaAdapter
        deleted = []

        class Stub(AlpacaAdapter):
            def __init__(self):
                self.base = "https://paper-api.alpaca.markets"
            def open_orders(self, nested=False):
                return [
                    # an unfilled bracket parent: still carries its legs
                    {"id": "parent-1", "symbol": "AAA", "legs": [
                        {"id": "l1", "type": "stop"}, {"id": "l2", "type": "limit"}]},
                    # a live stop protecting a FILLED position: no legs of its own
                    {"id": "leg-live", "symbol": "BBB", "type": "stop", "legs": []},
                    # a live take-profit, likewise
                    {"id": "leg-tp", "symbol": "BBB", "type": "limit"},
                ]
            def _request(self, method, url, body=None):
                deleted.append((method, url.rsplit("/", 1)[-1]))
                return {}

        out = Stub().cancel_unfilled_entries()
        self.assertEqual(deleted, [("DELETE", "parent-1")])
        self.assertEqual(out, ["AAA:parent-1"])
        # The two BBB legs are still resting. cancel_all() would have taken
        # them and left an open position with no stop.

    def test_a_failed_cancel_is_reported_not_swallowed(self):
        from adapters.alpaca import AlpacaAdapter
        from adapters.base import AdapterError

        class Stub(AlpacaAdapter):
            def __init__(self):
                self.base = "https://paper-api.alpaca.markets"
            def open_orders(self, nested=False):
                return [{"id": "p1", "symbol": "AAA", "legs": [{"id": "l1"}]}]
            def _request(self, method, url, body=None):
                raise AdapterError("HTTP 422: order is no longer cancelable")

        out = Stub().cancel_unfilled_entries()
        self.assertEqual(len(out), 1)
        self.assertIn("FAILED", out[0])


class TestUnprotectedPositionsAreDetectedHonestly(unittest.TestCase):
    """Measured 2026-09-18: when a bracket entry fills, the take-profit leg
    surfaces first and carries order_class="bracket". The old check counted
    any bracket-class order as protection, so a position with its stop gone
    and its take-profit intact read as protected. This is the control that
    decides whether the close escalates, so it has to test for a stop.
    """

    def _stub(self, orders, positions):
        from adapters.alpaca import AlpacaAdapter

        class Stub(AlpacaAdapter):
            def __init__(self):
                self.base = "https://paper-api.alpaca.markets"
            def _request(self, method, url, body=None):
                return orders
            def positions(self):
                return positions
        return Stub()

    def test_a_take_profit_alone_is_not_protection(self):
        a = self._stub(
            [{"id": "1", "symbol": "AAA", "type": "limit",
              "order_class": "bracket", "status": "new", "legs": []}],
            [{"symbol": "AAA", "qty": 1.0}])
        self.assertEqual(a.positions_without_stops(), ["AAA"])

    def test_a_live_stop_is_protection(self):
        a = self._stub(
            [{"id": "1", "symbol": "AAA", "type": "stop",
              "order_class": "bracket", "status": "new", "legs": []}],
            [{"symbol": "AAA", "qty": 1.0}])
        self.assertEqual(a.positions_without_stops(), [])

    def test_a_held_leg_counts_because_status_open_hides_it(self):
        # A bracket's legs sit `held` until the parent fills. They are real
        # and they will execute; a flat status=open listing does not show them.
        a = self._stub(
            [{"id": "1", "symbol": "AAA", "type": "limit",
              "order_class": "bracket", "status": "filled", "legs": [
                  {"id": "2", "type": "limit", "status": "held"},
                  {"id": "3", "type": "stop", "status": "held"}]}],
            [{"symbol": "AAA", "qty": 1.0}])
        self.assertEqual(a.positions_without_stops(), [])

    def test_a_cancelled_stop_is_not_protection(self):
        a = self._stub(
            [{"id": "1", "symbol": "AAA", "type": "limit",
              "order_class": "bracket", "status": "filled", "legs": [
                  {"id": "2", "type": "limit", "status": "new"},
                  {"id": "3", "type": "stop", "status": "canceled"}]}],
            [{"symbol": "AAA", "qty": 1.0}])
        self.assertEqual(a.positions_without_stops(), ["AAA"])

    def test_a_stop_on_a_different_symbol_does_not_protect_this_one(self):
        a = self._stub(
            [{"id": "1", "symbol": "BBB", "type": "stop",
              "order_class": "bracket", "status": "new", "legs": []}],
            [{"symbol": "AAA", "qty": 1.0}])
        self.assertEqual(a.positions_without_stops(), ["AAA"])



class TestHeldIsTheNormalRestingStateForAStop(unittest.TestCase):
    """`held` means MONITORED, not broken — and this codebase got that wrong
    in both directions inside 24 hours, so it is pinned here.

    Alpaca's Dan Whitnable, in
    https://forum.alpaca.markets/t/half-of-bracket-order-held/2727 :

        "Being 'held' simply means it hasn't been sent to the exchange yet."
        "Until the market price reaches that value, it is 'held'... In the
         background, the price is being monitored. If/when the price reaches
         the stop price then the stop-loss order will 'un-held'."
        "...the stop loss order is now submitted and the state is changed
         from 'held' to 'new'."

    A limit sell can rest on an exchange book; a stop cannot, so the broker
    watches the price and routes it on the trigger. A filled bracket showing
    take-profit `new` and stop `held` is therefore CORRECT.

    On 2026-09-23 that asymmetry was read as a broken stop and a position was
    flattened over it, realising -0.37 on a misreading. These tests exist so
    the next person to notice the asymmetry finds the answer instead of
    rediscovering the wrong one.
    """

    def _adapter(self, stop_status, tp_status="new", position=True):
        a = AlpacaAdapter.__new__(AlpacaAdapter)
        a.base = "https://paper-api.alpaca.markets"
        a._request = lambda m, u: [{
            "symbol": "DT", "status": "filled", "order_class": "bracket",
            "legs": [
                {"type": "limit", "status": tp_status, "limit_price": "63.81"},
                {"type": "stop", "status": stop_status, "stop_price": "55.80"},
            ]}]
        a.positions = lambda: ([{"symbol": "DT", "qty": 1.0,
                                 "avg_price": 58.47, "market_value": 58.25,
                                 "unrealized_pl": -0.22}] if position else [])
        return a

    def test_held_counts_as_protection(self):
        # The exact live shape from 2026-09-23: parent filled, TP new, stop held.
        self.assertEqual(self._adapter("held").positions_without_stops(), [])

    def test_held_is_in_active_statuses_and_must_stay_there(self):
        # A regression guard on the constant itself. Removing `held` would
        # report every correctly-bracketed position as naked, and session-close
        # treats that as a flatten-or-fix event.
        self.assertIn("held", AlpacaAdapter.ACTIVE_STATUSES)

    def test_a_triggered_stop_reading_new_is_also_protection(self):
        # The other side of the documented transition, held -> new.
        self.assertEqual(self._adapter("new").positions_without_stops(), [])

    def test_a_cancelled_stop_is_NOT_protection(self):
        # What a genuinely missing stop looks like, so the check still bites.
        self.assertEqual(self._adapter("canceled").positions_without_stops(),
                         ["DT"])

    def test_a_take_profit_alone_is_not_protection(self):
        # B-20's original finding, still pinned: a live limit leg with no stop
        # leg at all must not read as protected.
        a = AlpacaAdapter.__new__(AlpacaAdapter)
        a.base = "https://paper-api.alpaca.markets"
        a._request = lambda m, u: [{
            "symbol": "DT", "status": "filled", "order_class": "bracket",
            "legs": [{"type": "limit", "status": "new", "limit_price": "63.81"}]}]
        a.positions = lambda: [{"symbol": "DT", "qty": 1.0, "avg_price": 58.47,
                                "market_value": 58.25, "unrealized_pl": -0.22}]
        self.assertEqual(a.positions_without_stops(), ["DT"])
