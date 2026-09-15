#!/usr/bin/env python3
"""Account status. Run this before forming any market opinion."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.config import DEFAULT
from tools import state


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
    print(f"realized P&L    : ${d['realized_pnl']:,.2f}")
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
