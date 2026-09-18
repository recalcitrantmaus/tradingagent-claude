"""Alpaca adapter — paper by default, live only with same-day authorization.

Alpaca publishes a documented trading API with a free paper-trading endpoint
and market data, which is why it is the recommended substrate for Phase 2:
https://docs.alpaca.markets/

Endpoints used:
  paper trading  https://paper-api.alpaca.markets
  live trading   https://api.alpaca.markets
  market data    https://data.alpaca.markets

Auth is two headers, APCA-API-KEY-ID and APCA-API-SECRET-KEY, read from the
environment. Keys are never written to disk or logged by this module.

Standard library only (urllib), so the agent has no dependency to install and
nothing to keep patched.
"""

from typing import Dict, List, Optional
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import AdapterError, Authorization, OrderTicket

PAPER_TRADING = "https://paper-api.alpaca.markets"
LIVE_TRADING = "https://api.alpaca.markets"
DATA = "https://data.alpaca.markets"


class AlpacaAdapter:
    name = "alpaca"

    def __init__(self, live: bool = False, timeout: int = 20,
                 key_id: Optional[str] = None, secret: Optional[str] = None):
        self.live = live
        self.timeout = timeout
        self.base = LIVE_TRADING if live else PAPER_TRADING
        self._key = key_id or os.environ.get("ALPACA_API_KEY_ID")
        self._secret = secret or os.environ.get("ALPACA_API_SECRET_KEY")
        if not (self._key and self._secret):
            raise AdapterError(
                "set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY. Paper keys "
                "are free at https://app.alpaca.markets/ — never put live keys "
                "in a repo or a shell history file.")

    # ---------------------------------------------------------------- http
    def _headers(self) -> Dict[str, str]:
        return {"APCA-API-KEY-ID": self._key,
                "APCA-API-SECRET-KEY": self._secret,
                "Content-Type": "application/json",
                "User-Agent": "tradingagent-claude/1.0"}

    def _request(self, method: str, url: str, body: Optional[Dict] = None) -> Dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:500]
            raise AdapterError(f"{method} {url} -> HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise AdapterError(
                f"{method} {url} unreachable: {e.reason}. If this is a sandbox "
                "with an egress policy, the host is probably blocked — see "
                "docs/03-environment-constraints.md.") from e

    # ------------------------------------------------------------- reading
    def clock(self) -> Dict:
        return self._request("GET", f"{self.base}/v2/clock")

    def account(self) -> Dict:
        a = self._request("GET", f"{self.base}/v2/account")
        return {"equity": float(a.get("equity", 0)),
                "cash": float(a.get("cash", 0)),
                "buying_power": float(a.get("buying_power", 0)),
                "daytrade_count": int(a.get("daytrade_count", 0)),
                "pattern_day_trader": bool(a.get("pattern_day_trader", False)),
                "trading_blocked": bool(a.get("trading_blocked", False)),
                "raw": a}

    def positions(self) -> List[Dict]:
        rows = self._request("GET", f"{self.base}/v2/positions")
        return [{"symbol": p["symbol"], "qty": float(p["qty"]),
                 "avg_price": float(p["avg_entry_price"]),
                 "market_value": float(p["market_value"]),
                 "unrealized_pl": float(p["unrealized_pl"])} for p in rows]

    def open_orders(self) -> List[Dict]:
        q = urllib.parse.urlencode({"status": "open"})
        return self._request("GET", f"{self.base}/v2/orders?{q}")

    def order(self, order_id: str) -> Dict:
        return self._request("GET", f"{self.base}/v2/orders/{order_id}")

    # Terminal in the sense that matters here: the order will not fill later.
    TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "expired",
                         "rejected", "done_for_day", "stopped", "suspended"}

    def await_fill(self, order_id: str, seconds: float = 20.0,
                   interval: float = 2.0) -> Dict:
        """Poll one order until it resolves, or report it still working.

        Submitting is not filling. A bracket limit sent at the last trade can
        rest for hours, and an unfilled order is not a position. The caller
        must not write one to the fill log: it would sit at the head of that
        symbol's FIFO queue and corrupt the entry price and R of the next real
        trade, and it would accrue toward the 30 closed trades that unlock the
        option sleeve. Exactly the damage `closed_trades` already documents
        for dry-run rows, arriving through the live path instead.

        Returns the order with `filled_qty` and `filled_avg_price` coerced to
        numbers, plus `resolved`: True once the order reached a terminal
        state, False if it was still working when the clock ran out.
        """
        deadline = time.monotonic() + seconds
        o: Dict = {}
        while True:
            o = self.order(order_id)
            if (o.get("status") or "").lower() in self.TERMINAL_STATUSES:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(interval)
        o["filled_qty"] = float(o.get("filled_qty") or 0)
        avg = o.get("filled_avg_price")
        o["filled_avg_price"] = float(avg) if avg else None
        o["resolved"] = (o.get("status") or "").lower() in self.TERMINAL_STATUSES
        return o

    def bars(self, symbol: str, limit: int = 250, timeframe: str = "1Day") -> List[Dict]:
        """The most recent `limit` bars, oldest first.

        Two Alpaca behaviours make the naive request silently wrong, and both
        are dangerous here because every stop and every size is computed from
        this series:

        1. `start` defaults to the beginning of the current day when omitted,
           so a request carrying only `limit` returns a single bar. Any
           lookback built on it (ATR, a 20-day breakout) then fails a length
           check and the symbol is skipped — which reads as "no setup today"
           rather than as broken data.
        2. `limit` truncates from the *start* of the window, not the end, so
           widening the window without taking the tail returns the oldest
           bars and leaves the caller pricing a stop off month-old data.

        So: ask for a window comfortably wider than the request, page to the
        end of it, and return the tail.
        """
        per_bar_days = 1.6 if timeframe.endswith(("Day", "Week", "Month")) else 0.01
        span = max(int(limit * per_bar_days) + 15, 5)
        start = (dt.date.today() - dt.timedelta(days=span)).isoformat()

        rows: List[Dict] = []
        token = None
        for _ in range(20):                      # bounded; never spin on a token
            params = {"timeframe": timeframe, "limit": 10000,
                      "adjustment": "split", "feed": "iex", "start": start}
            if token:
                params["page_token"] = token
            d = self._request(
                "GET",
                f"{DATA}/v2/stocks/{symbol}/bars?{urllib.parse.urlencode(params)}")
            rows.extend(d.get("bars", []))
            token = d.get("next_page_token")
            if not token:
                break

        return [{"date": b["t"][:10], "open": b["o"], "high": b["h"],
                 "low": b["l"], "close": b["c"], "volume": b["v"]}
                for b in rows[-limit:]]

    def positions_without_stops(self) -> List[str]:
        """Positions with no resting protective order. These are unmanaged
        risk and session-close treats them as a flatten-or-fix event."""
        protected = {o["symbol"] for o in self.open_orders()
                     if o.get("type") in ("stop", "stop_limit", "trailing_stop")
                     or o.get("order_class") in ("bracket", "oto", "oco")}
        return [p["symbol"] for p in self.positions() if p["symbol"] not in protected]

    # ------------------------------------------------------------- writing
    def submit(self, ticket: OrderTicket, confirm_live: bool = False) -> Dict:
        """Bracket order: entry + stop + optional take-profit, atomically.

        A stop is never a follow-up call. If the stop cannot be attached, the
        entry is not sent — a filled entry whose stop failed to register is
        exactly the unmanaged position this system exists to prevent.
        """
        notional = ticket.qty * ticket.limit_price

        if self.live:
            if not confirm_live:
                raise AdapterError(
                    "live=True requires confirm_live=True at the call site")
            auth = Authorization.load()
            if auth is None:
                raise AdapterError(
                    "no state/authorization.json; live trading needs a dated "
                    "human authorization. Paper trading needs none.")
            ok, why = auth.valid_for(dt.date.today(), notional)
            if not ok:
                raise AdapterError(f"authorization refused: {why}")

        body = {
            "symbol": ticket.symbol,
            "qty": str(ticket.qty),
            "side": ticket.side,
            "type": "limit",
            "limit_price": f"{ticket.limit_price:.2f}",
            "time_in_force": ticket.time_in_force,
            "order_class": "bracket",
            "stop_loss": {"stop_price": f"{ticket.stop_price:.2f}"},
        }
        if ticket.take_profit:
            body["take_profit"] = {"limit_price": f"{ticket.take_profit:.2f}"}
        else:
            # Alpaca brackets require both legs; use a far target that the
            # trailing logic will replace rather than a fictional one.
            body["take_profit"] = {"limit_price": f"{ticket.limit_price * 3:.2f}"}
        return self._request("POST", f"{self.base}/v2/orders", body)

    def cancel_unfilled_entries(self) -> List[str]:
        """Cancel resting ENTRY orders, leaving protective legs alone.

        Entries are GTC so that a filled position's stop survives the close.
        The side effect is that an entry which did not fill would also survive,
        and fire tomorrow on a gap against a thesis written yesterday. So the
        close cancels entries — and only entries.

        cancel_all() must never be used for this: once a bracket parent fills,
        its stop and target become ordinary open orders, and cancelling them
        strips the protection off an open position. An unfilled bracket parent
        is identifiable because it still carries its `legs`; a live protective
        leg does not.
        """
        cancelled = []
        for o in self.open_orders():
            if not o.get("legs"):
                continue                      # a live leg, or a bare order
            oid = o.get("id")
            try:
                self._request("DELETE", f"{self.base}/v2/orders/{oid}")
                cancelled.append(f"{o.get('symbol')}:{oid}")
            except AdapterError as e:
                cancelled.append(f"{o.get('symbol')}:{oid} FAILED {str(e)[:80]}")
        return cancelled

    def cancel_all(self) -> Dict:
        return self._request("DELETE", f"{self.base}/v2/orders")

    def close_position(self, symbol: str) -> Dict:
        return self._request("DELETE", f"{self.base}/v2/positions/{symbol}")


class DryRunAlpaca(AlpacaAdapter):
    """Reads real data, prints orders instead of sending them.

    This is the default for Phase 2. It exercises the whole pipeline — data,
    the risk gate, ticket construction — with nothing at stake.
    """
    name = "alpaca-dryrun"

    def __init__(self, **kw):
        super().__init__(live=False, **kw)
        self.sent: List[OrderTicket] = []

    def submit(self, ticket: OrderTicket, confirm_live: bool = False) -> Dict:
        self.sent.append(ticket)
        print(f"[DRY RUN] would submit: {ticket.human()}")
        return {"dry_run": True, "ticket": ticket.human()}

    def await_fill(self, order_id: str, seconds: float = 20.0,
                   interval: float = 2.0) -> Dict:
        """Nothing was sent, so nothing can fill. Resolved, with zero filled."""
        return {"status": "dry_run", "filled_qty": 0.0,
                "filled_avg_price": None, "resolved": True, "dry_run": True}

    def cancel_unfilled_entries(self) -> List[str]:
        print("[DRY RUN] would cancel resting entry orders")
        return []

    def cancel_all(self) -> Dict:
        print("[DRY RUN] would cancel all open orders")
        return {"dry_run": True}
