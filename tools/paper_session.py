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
from engine.portfolio import Portfolio
from engine.risk import RiskOfficer, OrderProposal, State
from tools import state
from tools.review import closed_trades

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
        if len(bars) < 21:
            continue
        a = atr(bars, 14)
        if not a:
            continue
        px = bars[-1].close
        prior_high = max(b.high for b in bars[-21:-1])
        if px > prior_high:
            out.append(OrderProposal(
                symbol=sym, asset_class="equity", side="buy", price=px,
                stop=max(px - 1.5 * a, px * 0.92), target=px + 3.0 * a,
                thesis=f"20-day breakout over {prior_high:.2f}, ATR {a:.2f}"))
    return out


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
    for p in broker_positions:
        pf.positions[p["symbol"]] = __import__(
            "engine.portfolio", fromlist=["Position"]).Position(
            symbol=p["symbol"], asset_class="equity", qty=p["qty"],
            avg_price=p["avg_price"], opened_at=today)

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
    sent = 0
    for p in proposals:
        d = ro.evaluate(p, pf, prices, today)
        if not d.approved:
            print(f"  REJECT {p.symbol}: {d.reasons[0]}")
            continue
        ticket = OrderTicket(
            symbol=p.symbol, asset_class=p.asset_class, side=p.side,
            qty=d.qty, limit_price=round(p.price, 2),
            stop_price=round(p.stop, 2),
            take_profit=round(p.target, 2) if p.target else None,
            thesis=p.thesis)
        print(f"  APPROVE {p.symbol}: {d.reasons[-1]}")
        result = adapter.submit(ticket)
        state.append_fill({"symbol": p.symbol, "side": "buy", "qty": d.qty,
                           "price": p.price, "stop": p.stop, "fees": 0.0,
                           "multiplier": p.multiplier, "reason": "entry",
                           "thesis": p.thesis, "dry_run": bool(result.get("dry_run"))})
        sent += 1

    ledger["last_reconciled"] = today.isoformat()
    ledger["peak_equity"] = pf.peak_equity
    state.save(ledger)
    print(f"\n{sent} order(s) {'submitted' if args.submit else 'previewed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
