#!/usr/bin/env python3
"""The mechanical spine of a Phase 2 trading day.

The skills supply judgment. This supplies the things that must happen the same
way every day regardless of what the agent thinks about the market:

    python3 -m tools.trading_day open     # preflight, reconcile, mark, halts
    python3 -m tools.trading_day close    # reconcile, stop audit, mark, report
    python3 -m tools.trading_day week     # expectancy, costs, findings

Every subcommand reconciles against the broker first. A ledger that disagrees
with the broker is a stop-everything event: trading on a stale ledger is how a
bounded loss becomes an unbounded one.

--offline uses public market data and the stored ledger, for rehearsing the
flow before broker keys exist. It refuses to mark the day as traded.
"""
import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.portfolio import Portfolio, Position
from engine.risk import RiskOfficer, State
from tools import state
from tools.review import closed_trades

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "state" / "reports"


# ----------------------------------------------------------------------
# broker access
# ----------------------------------------------------------------------
def get_broker(offline: bool):
    if offline:
        return None
    from adapters.alpaca import AlpacaAdapter
    return AlpacaAdapter(live=False)


def reconcile(broker, ledger: Dict) -> Tuple[bool, List[str], Dict]:
    """Compare the broker's truth against ours. Returns (ok, notes, snapshot)."""
    notes: List[str] = []
    if broker is None:
        curve = ledger.get("equity_curve") or []
        eq = curve[-1][1] if curve else ledger.get("cash", DEFAULT.starting_equity)
        return True, ["OFFLINE: using the stored ledger, not the broker"], {
            "equity": eq, "cash": ledger["cash"], "positions": [],
            "unprotected": [], "daytrades": len(ledger.get("day_trades", []))}

    acct = broker.account()
    positions = broker.positions()
    unprotected = broker.positions_without_stops()

    if acct["trading_blocked"]:
        notes.append("BROKER REPORTS trading_blocked — stop")
    ledger_syms = set(ledger.get("positions", {}))
    broker_syms = {p["symbol"] for p in positions}
    if ledger_syms != broker_syms:
        only_ledger = ledger_syms - broker_syms
        only_broker = broker_syms - ledger_syms
        if only_ledger:
            notes.append(f"in ledger but NOT at broker: {sorted(only_ledger)}")
        if only_broker:
            notes.append(f"at broker but NOT in ledger: {sorted(only_broker)}")
    if unprotected:
        notes.append(f"positions with NO resting stop: {unprotected}")

    ok = not acct["trading_blocked"] and ledger_syms == broker_syms
    return ok, notes, {"equity": acct["equity"], "cash": acct["cash"],
                       "positions": positions, "unprotected": unprotected,
                       "daytrades": acct["daytrade_count"]}


def build_engine(snapshot: Dict, ledger: Dict, today: dt.date
                 ) -> Tuple[Portfolio, RiskOfficer]:
    pf = Portfolio(ledger.get("starting_equity", DEFAULT.starting_equity))
    pf.cash = snapshot["cash"]
    pf.peak_equity = max(ledger.get("peak_equity", snapshot["equity"]),
                         snapshot["equity"])
    for p in snapshot["positions"]:
        pf.positions[p["symbol"]] = Position(
            symbol=p["symbol"], asset_class="equity", qty=p["qty"],
            avg_price=p["avg_price"], opened_at=today)

    ro = RiskOfficer(DEFAULT)
    ro.day_start_equity = ledger.get("day_start_equity", snapshot["equity"])
    ro.week_start_equity = ledger.get("week_start_equity", snapshot["equity"])
    try:
        ro.state = State(ledger.get("risk_state", "NORMAL"))
    except ValueError:
        ro.state = State.NORMAL

    rs = [t["R"] for t in closed_trades(state.read_fills()) if t["R"] is not None]
    ro.set_track_record(len(rs), statistics.mean(rs) if rs else 0.0)
    return pf, ro


def prices_of(snapshot: Dict) -> Dict[str, float]:
    return {p["symbol"]: (p["market_value"] / p["qty"]) if p["qty"] else 0.0
            for p in snapshot["positions"]}


# ----------------------------------------------------------------------
# subcommands
# ----------------------------------------------------------------------
def cmd_open(args) -> int:
    today = dt.date.today()
    ledger = state.load()
    broker = get_broker(args.offline)
    ok, notes, snap = reconcile(broker, ledger)

    print(f"=== OPEN {today} ===")
    print(f"equity        ${snap['equity']:,.2f}   cash ${snap['cash']:,.2f}")
    for n in notes:
        print(f"  ! {n}")
    if not ok:
        print("\nRECONCILIATION FAILED — do not trade. Resolve the discrepancy "
              "above, by hand if necessary, before any order.")
        return 1

    pf, ro = build_engine(snap, ledger, today)
    prices = prices_of(snap)

    # A new week resets the weekly anchor; a new day resets the daily one.
    if today.weekday() == 0 or not ledger.get("week_start_equity"):
        ledger["week_start_equity"] = snap["equity"]
    ro.week_start_equity = ledger["week_start_equity"]
    ro.start_day(today, snap["equity"])
    ledger["day_start_equity"] = snap["equity"]

    st = ro.update(today, pf, prices)
    wk = (snap["equity"] / ledger["week_start_equity"] - 1) if ledger["week_start_equity"] else 0.0

    print(f"week-to-date  {wk:+.2%}   drawdown {pf.drawdown(prices):.2%} "
          f"(lock at {DEFAULT.max_drawdown_lock_pct:.0%})")
    print(f"risk state    {st.value}")
    print(f"track record  {ro.closed_trades} closed trades, "
          f"expectancy {ro.expectancy_R:+.3f}R")
    print(f"day trades    {snap['daytrades']} / {DEFAULT.max_day_trades_per_5d}")
    print(f"options       {'unlocked' if ro.closed_trades >= DEFAULT.option_min_closed_trades and ro.expectancy_R >= DEFAULT.option_min_expectancy_R and snap['equity'] >= DEFAULT.option_min_equity else 'LOCKED'}")
    if snap["positions"]:
        print("\nopen positions:")
        for p in snap["positions"]:
            flag = "  !! NO STOP" if p["symbol"] in snap["unprotected"] else ""
            print(f"  {p['symbol']:8} qty {p['qty']:>8g} @ {p['avg_price']:>9.2f} "
                  f"P&L {p['unrealized_pl']:>+8.2f}{flag}")

    ledger["risk_state"] = st.value
    ledger["peak_equity"] = pf.peak_equity
    ledger["last_reconciled"] = today.isoformat()
    ledger["positions"] = {p["symbol"]: p for p in snap["positions"]}
    if ro.journal:
        ledger.setdefault("halts", []).extend(
            [{"date": today.isoformat(), "event": j} for j in ro.journal])
    if not args.offline:
        state.save(ledger)

    if st != State.NORMAL:
        print(f"\n*** {st.value}: no new risk. Manage open positions only.")
        if st == State.LOCKED:
            print("*** LOCKED requires a human. Do not trade. Escalate today.")
        return 1
    print("\nNORMAL. Proceed to the premarket-brief skill.")
    return 0


def cmd_close(args) -> int:
    today = dt.date.today()
    ledger = state.load()
    broker = get_broker(args.offline)
    ok, notes, snap = reconcile(broker, ledger)

    pf, ro = build_engine(snap, ledger, today)
    prices = prices_of(snap)
    eq = snap["equity"]
    day_start = ledger.get("day_start_equity", eq)
    week_start = ledger.get("week_start_equity", eq)
    start = ledger.get("starting_equity", DEFAULT.starting_equity)

    day_pnl = eq / day_start - 1 if day_start else 0.0
    wk_pnl = eq / week_start - 1 if week_start else 0.0
    st = ro.update(today, pf, prices)

    # Overnight risk: stops do not hold through gaps, so price the 2x case.
    risk_1x = risk_2x = 0.0
    for p in snap["positions"]:
        pos = pf.positions[p["symbol"]]
        stop = ledger.get("positions", {}).get(p["symbol"], {}).get("stop")
        px = prices.get(p["symbol"], pos.avg_price)
        if stop:
            risk_1x += (px - stop) * pos.qty
            risk_2x += (px - stop) * 2 * pos.qty
        else:
            risk_1x += px * pos.qty * 0.10     # no stop: assume a bad 10% night
            risk_2x += px * pos.qty * 0.20

    lines = [
        f"# Session report — {today}",
        "",
        f"Equity: ${eq:,.2f} (day {day_pnl:+.2%}, week {wk_pnl:+.2%}, "
        f"since inception {eq / start - 1:+.2%})",
        f"Risk state: {st.value}",
        f"Drawdown from peak: {pf.drawdown(prices):.2%}",
        f"Track record: {ro.closed_trades} closed trades, "
        f"expectancy {ro.expectancy_R:+.3f}R",
        "",
        "## Overnight risk",
        f"If every stop fills at its level: -${risk_1x:,.2f} "
        f"({risk_1x / eq:.2%} of equity)" if eq else "n/a",
        f"If they all gap 2x through: -${risk_2x:,.2f} "
        f"({risk_2x / eq:.2%} of equity)" if eq else "n/a",
    ]
    if eq and risk_2x / eq > DEFAULT.weekly_loss_halt_pct:
        lines.append(f"**2x-gap loss exceeds the {DEFAULT.weekly_loss_halt_pct:.0%} "
                     "weekly halt — reduce overnight exposure now.**")

    lines += ["", "## Open overnight"]
    if snap["positions"]:
        for p in snap["positions"]:
            flag = "  **NO STOP — flatten or fix**" if p["symbol"] in snap["unprotected"] else ""
            lines.append(f"- {p['symbol']} qty {p['qty']:g} @ {p['avg_price']:.2f}, "
                         f"P&L {p['unrealized_pl']:+.2f}{flag}")
    else:
        lines.append("- none (flat)")

    if notes:
        lines += ["", "## Reconciliation notes"] + [f"- {n}" for n in notes]

    lines += ["", "## Escalate to the human today?"]
    escalations = []
    if st == State.LOCKED:
        escalations.append("risk state is LOCKED — only a human can clear it")
    if not ok:
        escalations.append("the ledger did not reconcile")
    if snap["unprotected"]:
        escalations.append(f"unprotected positions: {snap['unprotected']}")
    if wk_pnl <= -DEFAULT.weekly_loss_halt_pct:
        escalations.append(f"weekly loss {wk_pnl:.2%}")
    if ro.closed_trades >= 20 and ro.expectancy_R <= 0:
        escalations.append(f"expectancy {ro.expectancy_R:+.3f}R over "
                           f"{ro.closed_trades} trades is not positive")
    lines += [f"- {e}" for e in escalations] or ["- nothing"]

    report = "\n".join(lines)
    print(report)

    if not args.offline:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{today.isoformat()}.md").write_text(report + "\n")
        curve = ledger.setdefault("equity_curve", [])
        curve.append([today.isoformat(), eq])
        ledger["peak_equity"] = max(ledger.get("peak_equity", eq), eq)
        ledger["risk_state"] = st.value
        ledger["last_reconciled"] = today.isoformat()
        ledger.setdefault("days", []).append(
            {"date": today.isoformat(), "equity": eq, "day_pnl": round(day_pnl, 5),
             "risk_state": st.value, "escalations": escalations})
        state.save(ledger)
        print(f"\nwrote state/reports/{today.isoformat()}.md")

    return 1 if escalations else 0


def cmd_week(args) -> int:
    ledger = state.load()
    trades = closed_trades(state.read_fills())
    days = ledger.get("days", [])[-5:]
    start = ledger.get("week_start_equity") or ledger.get("starting_equity", 300.0)
    eq = days[-1]["equity"] if days else start

    rs = [t["R"] for t in trades if t["R"] is not None]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    costs = sum(t["fees"] for t in trades)
    net = sum(t["pnl"] for t in trades)

    print("=== WEEK REVIEW ===")
    print(f"equity          ${eq:,.2f}  (week {eq / start - 1:+.2%})")
    print(f"target gap      {eq / start - 1:+.2%} vs +5.00% "
          f"-> {(eq / start - 1) - 0.05:+.2%}")
    print(f"sessions        {len(days)}")
    print(f"closed trades   {len(trades)} ({len(wins)}W / {len(losses)}L)")
    if trades:
        print(f"win rate        {len(wins) / len(trades):.1%}")
        print(f"net P&L         ${net:,.2f}")
        print(f"costs           ${costs:,.2f}"
              f"{'   <-- COSTS EXCEED GAINS: trading too often' if costs > max(net, 0) else ''}")
    if rs:
        e = statistics.mean(rs)
        print(f"expectancy      {e:+.3f}R over {len(rs)} trades"
              f"{'   <-- NEGATIVE EDGE' if e <= 0 else ''}")
    else:
        print("expectancy      not measurable yet (no closed trades with a stop)")

    print("\n--- Phase 2 exit criteria ---")
    crit = [
        ("30+ closed trades", len(trades) >= 30, f"{len(trades)}/30"),
        ("positive expectancy", bool(rs) and statistics.mean(rs) > 0,
         f"{statistics.mean(rs):+.3f}R" if rs else "n/a"),
        ("zero guardrail breaches",
         not any(d.get("escalations") for d in ledger.get("days", [])),
         f"{sum(len(d.get('escalations', [])) for d in ledger.get('days', []))} escalations"),
        ("costs below gains", costs <= max(net, 0) if trades else True,
         f"${costs:,.2f} vs ${net:,.2f}"),
        ("never LOCKED", all(d.get("risk_state") != "LOCKED"
                             for d in ledger.get("days", [])), ""),
    ]
    for name, passed, detail in crit:
        print(f"  [{'ok' if passed else 'XX'}] {name:26} {detail}")
    print("\nNote: hitting +5% in a week is NOT an exit criterion. "
          "Report the gap; never close it with leverage.")
    return 0 if all(c[1] for c in crit) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["open", "close", "week"])
    ap.add_argument("--offline", action="store_true",
                    help="rehearse without a broker; does not persist state")
    a = ap.parse_args()
    return {"open": cmd_open, "close": cmd_close, "week": cmd_week}[a.command](a)


if __name__ == "__main__":
    raise SystemExit(main())
