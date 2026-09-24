#!/usr/bin/env python3
"""Account status. Run this before forming any market opinion."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.config import DEFAULT
from tools import state
from tools.review import closed_trades


def main() -> int:
    d = state.load()
    curve = d["equity_curve"]
    equity = curve[-1][1] if curve else d["cash"]
    peak = max(d["peak_equity"], equity)
    dd = (peak - equity) / peak if peak else 0.0

    print(f"mode            : {d['mode'].upper()}")
    print(f"equity          : ${equity:,.2f}  (start ${d['starting_equity']:,.2f}, "
          f"{equity / d['starting_equity'] - 1:+.2%})")
    print(f"cash            : ${d['cash']:,.2f}")
    # NOT d["realized_pnl"]. That field is initialised to 0.0 in state.EMPTY
    # and written by NOTHING — engine/portfolio.py keeps its own in-memory
    # counter, which never reaches the ledger. So the screen read before every
    # market opinion printed $0.00 on 2026-09-24 with a closed -$0.37 trade in
    # the fill log, which reads as "the loss is unrealized". A number that
    # cannot vary with what it claims to measure is worse than no number.
    # The fill log is the canonical record, so derive it from there.
    trades = closed_trades(state.read_fills())
    realized = sum(t["pnl"] for t in trades)
    print(f"realized P&L    : ${realized:,.2f}  ({len(trades)} closed "
          f"{'trade' if len(trades) == 1 else 'trades'})")
    if trades:
        Rs = [t["R"] for t in trades if t.get("R") is not None]
        if Rs:
            # The Phase 2 exit criterion, and the option unlock: 30+ closed
            # trades at >= +0.10R measured expectancy.
            exp = sum(Rs) / len(Rs)
            print(f"expectancy      : {exp:+.3f}R over {len(Rs)} trades "
                  f"(exit criterion: 30+ at >= +0.10R)")
    print(f"peak / drawdown : ${peak:,.2f} / {dd:.2%} "
          f"(lock at {DEFAULT.max_drawdown_lock_pct:.0%})")
    print(f"risk state      : {d['risk_state']}")
    print(f"day trades (5d) : {len(d['day_trades'])} / {DEFAULT.max_day_trades_per_5d}")
    unlocked = ("yes" if equity >= DEFAULT.option_min_equity
                else f"no (needs ${DEFAULT.option_min_equity:,.0f})")
    print(f"options unlocked: {unlocked}")
    print(f"last reconciled : {d['last_reconciled'] or 'NEVER — do not trade'}")
    if d["positions"]:
        print("\npositions:")
        for sym, p in d["positions"].items():
            print(f"  {sym:10s} qty {p['qty']:>8g} @ {p['avg_price']:>9.2f} "
                  f"stop {p.get('stop') or 'MISSING':>9}")
            if not p.get("stop"):
                print(f"  !! {sym} has no stop — flatten or set one before trading")
    else:
        print("\npositions: none")

    if d["risk_state"] != "NORMAL":
        print(f"\n*** {d['risk_state']}: no new risk. "
              f"{'A human must authorize resumption.' if d['risk_state'] == 'LOCKED' else ''}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
