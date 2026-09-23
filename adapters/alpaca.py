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

    def open_orders(self, nested: bool = False) -> List[Dict]:
        """Open orders. `nested=True` returns bracket parents with their legs
        populated, and does NOT list those legs as separate top-level rows.

        The default is flat because `positions_without_stops` depends on a
        FILLED parent's live protective legs appearing at the top level, where
        it can see their `type`. Measured 2026-09-18: without `nested`, an
        unfilled bracket parent comes back with `legs` absent entirely, which
        is why identifying parents by their legs needs this flag.
        """
        q = {"status": "open"}
        if nested:
            q["nested"] = "true"
        return self._request(
            "GET", f"{self.base}/v2/orders?{urllib.parse.urlencode(q)}")

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

    def bars(self, symbol: str, limit: int = 250, timeframe: str = "1Day",
             feed: str = "sip") -> List[Dict]:
        """The most recent `limit` bars, oldest first.

        THE FEED IS NOT A DETAIL (M-30, fixed 2026-09-22). This defaulted to
        `iex` because the free plan was believed to serve nothing else. It
        serves `sip`. IEX is one venue carrying a median 3.8% of consolidated
        volume, and a 3.8% sample does not misprice a mean — it misprices an
        EXTREMUM, which is the only statistic this series is used for.
        Measured across 59 universe names on 2026-09-22, completed sessions:

            ATR(14) IEX/SIP  : median 0.976, mean 0.936, worst 0.571
                               SMALLER IN 59 OF 59 NAMES
            20-day high      : understated in 43/59, worst -0.913%
            20-day low       : OVERstated  in 41/59, worst +0.487%

        One-directional, every one of them, for the arithmetic reason that a
        subset of prints cannot contain a higher high or a lower low than the
        whole. So the old default manufactured breakouts (1 of 59 names on the
        day measured), and set every stop too tight. Dollar risk at the stop
        survives that, because size follows the stop — but the share count
        does not, so gap exposure scales up with the error, and a stop placed
        inside the noise band is hit by noise.

        SIP is 15 minutes delayed on this plan; IEX is real-time. That is fine
        here and only here: these are COMPLETED sessions, which do not change.
        For anything that needs the price NOW — an entry, a cross-check — use
        `last_trade()`, which is real-time. Do not read `bars()[-1].close` as
        the current price; on this feed it is a quarter of an hour old.

        Two Alpaca behaviours also make the naive request silently wrong, and
        both are dangerous here because every stop and every size is computed
        from this series:

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
                      "adjustment": "split", "feed": feed, "start": start}
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

    def last_trade(self, symbol: str) -> Optional[float]:
        """The most recent trade price, REAL TIME.

        `bars()` is SIP and therefore 15 minutes stale by design (see there).
        Everything that acts on the price now — an entry, a stop distance
        measured from the live price, `cross_check` — has to come from here
        instead. Falls back to the snapshot's own daily bar close, which is
        also IEX and also real-time.

        Returns None rather than a guess: a missing price must stand down the
        symbol, never be filled in from a stale series.
        """
        try:
            d = (self._request(
                "GET", f"{DATA}/v2/stocks/snapshots?symbols={symbol}"
            ).get(symbol) or {})
        except AdapterError:
            return None
        px = ((d.get("latestTrade") or {}).get("p")
              or (d.get("dailyBar") or {}).get("c"))
        return float(px) if px else None

    # An order in one of these states can still execute. `held` matters most:
    # a bracket's legs sit held until the parent fills, and Alpaca's
    # status=open filter EXCLUDES held, so a stop can be perfectly in place
    # and invisible to a naive listing.
    ACTIVE_STATUSES = {"new", "accepted", "held", "partially_filled",
                       "pending_new", "accepted_for_bidding", "calculated",
                       "pending_replace", "replaced"}
    STOP_TYPES = ("stop", "stop_limit", "trailing_stop")

    def positions_without_stops(self) -> List[str]:
        """Positions with no live stop. Session-close treats these as a
        flatten-or-fix event, so the test has to mean what it says.

        It previously counted a symbol as protected if ANY open order on it
        carried `order_class` in (bracket, oto, oco). Measured 2026-09-18: when
        a bracket entry fills, the take-profit leg appears first and it carries
        `order_class="bracket"` — so a position was reported protected on the
        strength of a TAKE-PROFIT, and would have been reported protected with
        the stop leg missing entirely. A control that passes on the wrong
        evidence is worse than no control, because it is trusted.

        So: a real order, of a stop type, in a state that can still execute.
        Nested, because a held leg is invisible to a flat status=open listing.
        """
        q = urllib.parse.urlencode({"status": "all", "limit": "200",
                                    "direction": "desc", "nested": "true"})
        rows = self._request("GET", f"{self.base}/v2/orders?{q}")
        protected = set()
        for o in rows:
            for c in [o] + list(o.get("legs") or []):
                if (c.get("type") in self.STOP_TYPES
                        and (c.get("status") or "").lower() in self.ACTIVE_STATUSES):
                    protected.add(o.get("symbol"))
        return [p["symbol"] for p in self.positions()
                if p["symbol"] not in protected]

    def resting_stops(self) -> Dict[str, float]:
        """The live protective stop PRICE per symbol, not merely its existence.

        `positions_without_stops` answers "is this position protected at all",
        which is the flatten-or-fix question. It is not enough for
        `Portfolio.open_risk`, which needs the price to compute what the book
        actually loses if every stop fills.

        Without this the runner rebuilds broker positions with `stop=None`, and
        `open_risk` counts an unstopped position at FULL NOTIONAL — correctly,
        by its own rule, since an unstopped loss is unbounded. The result is a
        book that reads as 19% at risk against a 4% cap the moment any position
        is carried, so every subsequent entry is refused on the aggregate cap.
        That is not the cap working; it is the cap being fed a position whose
        stop is resting at the broker and simply was not asked for.

        Widest stop wins on a tie: two stops on one symbol means the protective
        one is whichever fires last, so the conservative reading of the risk is
        the lower stop price.
        """
        q = urllib.parse.urlencode({"status": "all", "limit": "200",
                                    "direction": "desc", "nested": "true"})
        out: Dict[str, float] = {}
        for o in self._request("GET", f"{self.base}/v2/orders?{q}"):
            sym = o.get("symbol")
            for c in [o] + list(o.get("legs") or []):
                if (c.get("type") in self.STOP_TYPES
                        and (c.get("status") or "").lower() in self.ACTIVE_STATUSES):
                    px = c.get("stop_price")
                    if px is None:
                        continue
                    px = float(px)
                    out[sym] = min(px, out[sym]) if sym in out else px
        return out

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
        for o in self.open_orders(nested=True):
            if not o.get("legs"):
                continue                      # a live leg, or a bare order
            # Belt and braces. Identifying parents by their legs is correct
            # but depends on a response shape that has already surprised us
            # once; a stop must never be cancellable by this method even if
            # that shape changes again.
            if o.get("type") in ("stop", "stop_limit", "trailing_stop"):
                continue
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
