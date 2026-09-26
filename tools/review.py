#!/usr/bin/env python3
"""Performance review from the fill log. Measures edge, not mood.

    python3 -m tools.review --week
    python3 -m tools.review --last 20
"""
import argparse
import datetime as dt
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import state


def closed_trades(fills):
    """Pair entries with exits per symbol; return realized trades with R.

    Dry-run fills are dropped before anything is paired. `paper_session`
    appends a record for every approved proposal including under --dry-run,
    tagged dry_run, and two things go wrong if they are counted: previewed
    tickets accrue toward the 30 closed trades and the measured expectancy
    that unlock the option sleeve, and a phantom dry-run *entry* sits at the
    head of the FIFO queue where it will pair against the next real sell of
    that symbol and corrupt that real trade's entry price and R.
    """
    fills = [f for f in fills if not f.get("dry_run")]
    open_lots, trades = {}, []
    for f in fills:
        sym = f["symbol"]
        if f["side"] == "buy":
            open_lots.setdefault(sym, []).append(f)
        else:
            lots = open_lots.get(sym) or []
            if not lots:
                continue
            entry = lots[0]
            mult = f.get("multiplier", 1)
            qty = min(f["qty"], entry["qty"])
            pnl = (f["price"] - entry["price"]) * qty * mult \
                - f.get("fees", 0) - entry.get("fees", 0)
            risk = (entry["price"] - entry.get("stop", entry["price"])) * qty * mult
            trades.append({
                "symbol": sym, "opened": entry["ts"], "closed": f["ts"],
                "pnl": pnl, "R": pnl / risk if risk > 0 else None,
                "reason": f.get("reason", ""),
                "fees": f.get("fees", 0) + entry.get("fees", 0),
            })
            entry["qty"] -= qty
            if entry["qty"] <= 1e-9:
                lots.pop(0)
    return trades


def day_trade_dates(fills):
    """The exchange date of every day trade in the fill log, oldest first.

    W-1 (2026-09-26). The budget used to be fed by `record_day_trade`, which
    nothing called, and by `ledger["day_trades"]`, which nothing wrote, so it
    read 0 through a real same-day round trip on 2026-09-23. The fill log is
    the canonical record of what traded, so the count is derived from it on
    every read rather than maintained beside it.

    A day trade is a live sell of a symbol after a live buy of that symbol on
    the same America/New_York trading date. A sell with no earlier same-day
    buy is a carry closing, not a day trade. Dry-run rows are previews and are
    dropped, as in `closed_trades`. A row whose timestamp cannot be read is
    dropped rather than guessed into a day.

    Counted conservatively: every live sell that follows a same-day buy of the
    symbol is one day trade, so a same-day scale-out in two pieces counts
    twice. How a regulator counts a split exit is not settled in this repo,
    and a count that errs high errs toward the limit, never past it.
    """
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    by_day = {}
    for f in fills:
        if f.get("dry_run"):
            continue
        raw = f.get("ts")
        try:
            when = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        key = (f.get("symbol"), when.astimezone(et).date())
        by_day.setdefault(key, []).append((when, f.get("side")))
    out = []
    for (_, day), rows in by_day.items():
        bought = False
        for _, side in sorted(rows, key=lambda r: r[0]):
            if side == "buy":
                bought = True
            elif side == "sell" and bought:
                out.append(day)
    return sorted(out)


def report(trades, label):
    if not trades:
        print(f"{label}: no closed trades")
        return
    pnls = [t["pnl"] for t in trades]
    rs = [t["R"] for t in trades if t["R"] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    fees = sum(t["fees"] for t in trades)

    print(f"\n=== {label} ===")
    print(f"trades          : {len(trades)}  ({len(wins)}W / {len(losses)}L)")
    print(f"win rate        : {len(wins) / len(trades):.1%}")
    print(f"net P&L         : ${sum(pnls):,.2f}")
    print(f"costs           : ${fees:,.2f}"
          f"{'  <-- COSTS EXCEED GAINS' if fees > max(sum(pnls), 0) else ''}")
    if wins:
        print(f"avg win         : ${statistics.mean(wins):,.2f}")
    if losses:
        print(f"avg loss        : ${statistics.mean(losses):,.2f}")
    if wins and losses:
        print(f"profit factor   : {sum(wins) / abs(sum(losses)):.2f}")
    if rs:
        e = statistics.mean(rs)
        print(f"expectancy      : {e:+.3f} R per trade"
              f"{'  <-- NEGATIVE EDGE' if e <= 0 else ''}")
        if len(rs) >= 20 and statistics.mean(rs[-20:]) <= 0:
            print("  last 20 trades are negative-expectancy: cut size to half")
        if len(rs) >= 40 and statistics.mean(rs[-40:]) <= 0:
            print("  last 40 trades are negative-expectancy: STOP and escalate")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", action="store_true")
    ap.add_argument("--last", type=int)
    args = ap.parse_args()

    trades = closed_trades(state.read_fills())
    if args.week:
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
        report([t for t in trades if t["closed"] >= cutoff], "last 7 days")
    if args.last:
        report(trades[-args.last:], f"last {args.last} trades")
    report(trades, "since inception")


if __name__ == "__main__":
    main()
