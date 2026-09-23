#!/usr/bin/env python3
"""Run one paper trading session against a real broker adapter.

This is the Phase 2 substrate: real prices, real account state, the real risk
engine, and tickets that are printed rather than sent unless you say otherwise.

    python3 -m tools.paper_session --dry-run
    python3 -m tools.paper_session --submit          # sends to Alpaca PAPER
    python3 -m tools.paper_session --symbols AAPL,F,SOFI --dry-run

The mechanical strategies here are a baseline, not the agent's brain. In live
operation the `trade-plan` skill produces the proposals and this runner's job
is only to gate and route them — which is why `propose_from_plan` reads the
plan JSON when one exists for today.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.alpaca import AlpacaAdapter, DryRunAlpaca
from adapters.base import AdapterError, OrderTicket
from dataclasses import replace

from engine.config import DEFAULT
from engine.posture import limits_for, for_date as posture_for
from engine.market import Bar, atr
from engine.portfolio import Portfolio, Position
from engine.risk import RiskOfficer, OrderProposal, State
from tools import state
from tools.review import closed_trades

# How long to wait for a marketable limit to resolve before calling it
# resting. Long enough for a normal fill, short enough that a session is
# not held open by an order that is plainly not going to trade.
FILL_WAIT_SECONDS = 30.0

# Kept only as the emergency fallback when data/universe.json is absent. Six
# hardcoded tickers were the real reason two sessions "found no setup": the
# screen was not thin, the candidate list was. See tools/screen.py.
FALLBACK_SYMBOLS = ["F", "SOFI", "PLTR", "NIO", "RIOT", "HOOD"]


def default_symbols() -> List[str]:
    """The committed universe, or the six-name fallback with a loud warning."""
    try:
        from tools.screen import load_universe
        return [r["symbol"] for r in load_universe()["symbols"]]
    except SystemExit:
        print("!! no data/universe.json — falling back to six hardcoded tickers. "
              "This is not a universe. Run: python3 -m tools.screen "
              "--build-universe", file=sys.stderr)
        return list(FALLBACK_SYMBOLS)
PLAN_DIR = Path(__file__).resolve().parents[1] / "state" / "plans"
BRIEF_DIR = Path(__file__).resolve().parents[1] / "state" / "briefs"


def _bars(rows: List[Dict]) -> List[Bar]:
    return [Bar(dt.date.fromisoformat(r["date"]), r["open"], r["high"],
                r["low"], r["close"], r["volume"]) for r in rows]


def propose_from_plan(today: dt.date) -> Optional[List[OrderProposal]]:
    """Today's plan from the trade-plan skill.

    Returns None when no plan file exists, and a list when one does — which
    may be empty. The distinction is the whole point: an empty plan is a
    deliberate decision to trade nothing, and it must not be confused with
    having no opinion. Returning [] for both let `x or mechanical()` discard a
    written refusal and substitute the breakout scanner's view instead.
    """
    p = PLAN_DIR / f"{today.isoformat()}.json"
    if not p.exists():
        return None
    out = []
    for row in json.loads(p.read_text()):
        out.append(OrderProposal(**row))
    print(f"loaded {len(out)} proposals from {p}")
    return out


def propose_mechanical(adapter, symbols: List[str]) -> List[OrderProposal]:
    """Baseline 20-day breakout, so the pipeline can be exercised with no plan."""
    out = []
    for sym in symbols:
        try:
            bars = _bars(adapter.bars(sym, limit=60))
        except AdapterError as e:
            print(f"  {sym}: data unavailable — {str(e)[:100]}")
            continue
        # Completed sessions only for the level and the ATR, and the price
        # from a real-time source. bars() is SIP since M-30 and its current
        # bar is both partial and 15 minutes stale; reading it as `px` would
        # have priced the entry, the stop AND the target off a quarter-hour-
        # old number.
        bars = [b for b in bars if b.date < dt.date.today()]
        if len(bars) < 21:
            continue
        a = atr(bars, 14)
        if not a:
            continue
        px = adapter.last_trade(sym)
        if px is None:
            print(f"  {sym}: no live price — standing down")
            continue
        prior_high = max(b.high for b in bars[-20:])
        if px > prior_high:
            out.append(OrderProposal(
                symbol=sym, asset_class="equity", side="buy", price=px,
                stop=max(px - 1.5 * a, px * 0.92), target=px + 3.0 * a,
                thesis=f"20-day breakout over {prior_high:.2f}, ATR {a:.2f}"))
    return out



REFUSED_STATUSES = ("rejected", "canceled", "cancelled", "expired")


def fill_record(p, qty_approved: float, ticket, order: Dict) -> Optional[Dict]:
    """The fill-log row an order outcome earns, or None if it earns nothing.

    Separated from main() so the rule can be tested without a broker. The rule
    is one sentence: **only an actual fill is written, and it is written at the
    price and quantity the broker reports, never at the proposed ones.**

    An order that is still working is not a position. Writing it would put a
    phantom entry at the head of that symbol's FIFO queue in closed_trades(),
    where it corrupts the entry price and R of the next real trade in that
    symbol, and it would count toward the 30 closed trades and the +0.10R
    expectancy that unlock the option sleeve. The dry-run path already
    documents that damage; this is the same damage through the live path.
    """
    qty = float(order.get("filled_qty") or 0)
    px = order.get("filled_avg_price")
    if qty <= 0 or not px:
        return None
    return {"symbol": p.symbol, "side": "buy", "qty": qty, "price": float(px),
            "stop": p.stop, "fees": 0.0, "multiplier": p.multiplier,
            "reason": "entry", "thesis": p.thesis, "dry_run": False,
            "order_id": order.get("id"), "limit_price": ticket.limit_price}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--submit", action="store_true",
                   help="actually send to the Alpaca PAPER endpoint")
    ap.add_argument("--symbols", default="")
    args = ap.parse_args()

    today = dt.date.today()
    try:
        adapter = AlpacaAdapter(live=False) if args.submit else DryRunAlpaca()
    except AdapterError as e:
        print(f"adapter unavailable: {e}")
        return 2

    # ---- 1. reconcile against the broker before anything else ----
    try:
        acct = adapter.account()
        broker_positions = adapter.positions()
        unprotected = adapter.positions_without_stops()
    except AdapterError as e:
        print(f"cannot reach the broker: {e}")
        return 2

    print(f"broker equity  : ${acct['equity']:,.2f}")
    print(f"buying power   : ${acct['buying_power']:,.2f}")
    print(f"day trades     : {acct['daytrade_count']}"
          f"{'  (flagged PDT)' if acct['pattern_day_trader'] else ''}")
    if acct["trading_blocked"]:
        print("!! broker reports trading_blocked — stop here")
        return 1
    if unprotected:
        print(f"!! positions with no resting stop: {unprotected}")
        print("   fix or flatten these before opening new risk")
        return 1

    # ---- 2. rebuild engine state from the broker, not from memory ----
    pf = Portfolio(acct["equity"])
    pf.cash = acct["cash"]
    ledger = state.load()
    pf.peak_equity = max(ledger.get("peak_equity", acct["equity"]), acct["equity"])
    # Carry each position's REAL resting stop across, not just the position.
    # `Portfolio.open_risk` counts a position with `stop=None` at full
    # notional — correct, because an unstopped loss is unbounded — so
    # rebuilding a stopped position without its stop reports a book at ~19% of
    # equity against a 4% cap and refuses every subsequent entry. The stop is
    # resting at the broker; it only had to be asked for.
    try:
        stops = adapter.resting_stops()
    except (AdapterError, AttributeError):
        stops = {}          # fail closed: no stop known, full notional at risk
    for p in broker_positions:
        pf.positions[p["symbol"]] = Position(
            symbol=p["symbol"], asset_class="equity", qty=p["qty"],
            avg_price=p["avg_price"], opened_at=today,
            stop=stops.get(p["symbol"]))

    ro = RiskOfficer(DEFAULT)
    ro.start_day(today, acct["equity"])
    trades = closed_trades(state.read_fills())
    rs = [t["R"] for t in trades if t["R"] is not None]
    ro.set_track_record(len(rs), sum(rs) / len(rs) if rs else 0.0)
    print(f"track record   : {len(rs)} closed trades, "
          f"expectancy {(sum(rs)/len(rs) if rs else 0):+.3f}R")

    prices = {p["symbol"]: p["market_value"] / p["qty"]
              for p in broker_positions if p["qty"]}
    if ro.update(today, pf, prices) != State.NORMAL:
        print(f"!! risk state {ro.state.value}: no new risk today")
        for j in ro.journal:
            print(f"   {j}")
        return 1

    # ---- 3. posture gate: the brief is binding, and it is checked here ----
    posture, note = posture_for(BRIEF_DIR, today)
    limits = limits_for(posture)
    print(f"posture        : {note}")
    if not limits.allows_new_risk:
        print(f"!! {limits.reason} — no entries. Exits remain permitted.")
        return 0
    if limits.max_risk_per_trade_pct is not None:
        ro.cfg = replace(
            ro.cfg,
            max_risk_per_trade_pct=limits.max_risk_per_trade_pct,
            max_concurrent_positions=(limits.max_concurrent_positions
                                      or ro.cfg.max_concurrent_positions))
        print(f"   {limits.reason}")

    # ---- 4. proposals: a written plan wins, even when it is empty ----
    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               or default_symbols())
    planned = propose_from_plan(today)
    if planned is None:
        proposals = propose_mechanical(adapter, symbols)
    else:
        proposals = planned          # [] means trade nothing, deliberately
        if not proposals:
            print("\nplan for today is empty — a deliberate NO-TRADE. "
                  "The mechanical scanner is NOT consulted.")
            return 0
    if not proposals:
        print("\nno proposals today. An empty plan is a valid outcome.")
        return 0

    # ---- 5. gate, then route ----
    print(f"\n{len(proposals)} proposal(s):")
    sent = filled = working = refused = 0
    resting: List[Dict] = []
    for p in proposals:
        d = ro.evaluate(p, pf, prices, today)
        if not d.approved:
            # reasons[-1], not reasons[0]. `Decision.reject` APPENDS the
            # binding constraint, while `evaluate` may already have appended
            # informational notes (the expected-R grade, for one) before
            # reaching it. Printing reasons[0] named whichever note happened to
            # land first: on 2026-09-23 a refusal on the tapered risk budget
            # was logged as "expected R 2.00", which is not a reason to refuse
            # anything — it is a passing grade. A refusal that names the wrong
            # constraint is worse than no log, because it reads as an audit
            # trail while pointing at the wrong control.
            print(f"  REJECT {p.symbol}: {d.reasons[-1]}")
            continue
        ticket = OrderTicket(
            symbol=p.symbol, asset_class=p.asset_class, side=p.side,
            qty=d.qty, limit_price=round(p.price, 2),
            stop_price=round(p.stop, 2),
            take_profit=round(p.target, 2) if p.target else None,
            thesis=p.thesis)
        print(f"  APPROVE {p.symbol}: {d.reasons[-1]}")

        # Reserve this order against the book BEFORE the next proposal is
        # gated. `RiskOfficer.evaluate` reads BOTH the concurrency taper
        # (`correlated_risk_decay ** len(portfolio.positions)`) and the T-1
        # aggregate open-risk cap (`portfolio.open_risk`) out of the portfolio
        # it is handed. This loop used to hand it the same untouched `pf` for
        # every proposal, so within one session every proposal was gated as
        # though it were the first: the taper never tapered and the 4% book cap
        # never bound. Four 2% proposals in one session restored exactly the 8%
        # book that T-1 was opened to prevent — the control landed in engine/
        # and was never wired into the caller.
        #
        # Reserved at APPROVAL rather than at fill, deliberately. A submitted
        # bracket has already committed the risk: the entry can fill a second
        # later and the stop rests behind it. Reserving early can only make the
        # engine refuse MORE, never less, which is the correct direction for
        # the one error this account cannot afford.
        pf.positions[p.symbol] = Position(
            symbol=p.symbol, asset_class=p.asset_class, qty=d.qty,
            avg_price=p.price, opened_at=today, stop=p.stop,
            target=p.target, multiplier=p.multiplier)
        pf.cash = max(0.0, pf.cash - d.qty * p.price * p.multiplier)

        result = adapter.submit(ticket)
        sent += 1

        # A dry run sends nothing, so there is nothing to wait for. The row is
        # still written, tagged, because the preview log is how a no-trade day
        # proves what it would have done; closed_trades() drops it.
        if result.get("dry_run"):
            state.append_fill({"symbol": p.symbol, "side": "buy", "qty": d.qty,
                               "price": p.price, "stop": p.stop, "fees": 0.0,
                               "multiplier": p.multiplier, "reason": "entry",
                               "thesis": p.thesis, "dry_run": True})
            continue

        # Submitting is not filling. Record what the broker actually did.
        oid = result.get("id")
        o = adapter.await_fill(oid, seconds=FILL_WAIT_SECONDS)
        status = (o.get("status") or "unknown").lower()
        qty, px = o.get("filled_qty") or 0.0, o.get("filled_avg_price")
        o.setdefault("id", oid)
        row = fill_record(p, d.qty, ticket, o)
        if row is not None:
            state.append_fill(row)
            filled += 1
            slip = (px - p.price) / p.price if p.price else 0.0
            print(f"    FILLED {qty:g} @ {px:.4f} "
                  f"(proposed {p.price:.4f}, slippage {slip:+.2%})")
            if qty < d.qty:
                print(f"    partial: {d.qty - qty:g} of {d.qty:g} still working")
                resting.append({"symbol": p.symbol, "order_id": oid,
                                "status": status, "unfilled_qty": d.qty - qty})
        elif status in REFUSED_STATUSES:
            refused += 1
            reason = (o.get("reject_reason") or o.get("status") or "")
            print(f"    {status.upper()} by the broker — nothing recorded"
                  f"{': ' + str(reason) if o.get('reject_reason') else ''}")
        else:
            working += 1
            resting.append({"symbol": p.symbol, "order_id": oid,
                            "status": status, "unfilled_qty": d.qty})
            print(f"    WORKING (status {status}) after {FILL_WAIT_SECONDS:.0f}s "
                  f"— no fill, nothing recorded. session-close must reconcile.")

    ledger["last_reconciled"] = today.isoformat()
    ledger["peak_equity"] = pf.peak_equity
    if args.submit:
        ledger["working_orders"] = resting
    state.save(ledger)
    if args.submit:
        print(f"\n{sent} order(s) submitted: {filled} filled, "
              f"{working} still working, {refused} refused by the broker")
        if resting:
            print("   resting orders carried into the ledger for session-close:")
            for r in resting:
                print(f"     {r['symbol']} {r['order_id']} ({r['status']})")
    else:
        print(f"\n{sent} order(s) previewed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
