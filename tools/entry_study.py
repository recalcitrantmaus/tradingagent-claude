#!/usr/bin/env python3
"""Chase the breakout, or wait for the retest? (D-24 / M-2)

Monday 2026-09-21 produced the question in the live account: the plan found a
real signal in ETHA, set a retest limit at the broken level rather than
chasing 2% higher, and never filled. ETHA closed +4.8%. The thesis was right
about direction and the account collected none of it.

One observation settles nothing — a squeeze that never gives the level back
simply does not fill, which the plan itself predicted. So measure it.

Two entry styles on the SAME signals, same universe, same stop rule, no target
(the best arm in docs/15), 20-day horizon from the fill:

  chase   buy at the next open, whatever it is
  retest  rest a limit at the broken level (the prior 20-day high); fill only
          if price trades back to it within `--wait` sessions, else no trade

The number that matters is not which wins on the trades it takes. It is what
the retest arm FORGOES: a breakout that never pulls back is the breakout you
most wanted, so a retest rule may be systematically selecting against its own
best outcomes — the same anti-selection the structural filter showed.

    python3 -m tools.entry_study --year 2026 --top 150 --wait 5
"""
import argparse
import datetime as dt
import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.market import Bar, atr
from tools.screen import LOOKBACK, ATR_PERIOD
from tools.pit_study import (CACHE, MA_PERIOD, classify, eligible,
                             liquidity_ranked_membership)
from tools.target_study import resolve, summarise


def run(year: int, horizon: int, wait: int, top: int, blob=None) -> Dict:
    blob = blob if blob is not None else json.load(gzip.open(CACHE, "rt"))
    names, raw = blob["names"], blob["bars"]
    member = liquidity_ranked_membership(raw, names, "plain", year, top) if top else None

    rows = {"chase": [], "retest": []}
    missed = []          # signals the retest arm never filled — the real cost
    signals = 0

    for sym, r in raw.items():
        if classify(names.get(sym, "")) != "plain":
            continue
        bars = [Bar(dt.date.fromisoformat(x[0]), x[1], x[2], x[3], x[4], x[5])
                for x in r]
        if len(bars) < MA_PERIOD + LOOKBACK + ATR_PERIOD + 5:
            continue
        for i in range(MA_PERIOD, len(bars) - 1):
            b = bars[i]
            if b.date.year != year or not eligible(bars, i):
                continue
            if member is not None and sym not in member.get(b.date.isoformat(), ()):
                continue
            prior_high = max(x.high for x in bars[i - LOOKBACK:i])
            if b.close <= prior_high:
                continue
            a = atr(bars[:i + 1], ATR_PERIOD)
            if not a:
                continue
            signals += 1

            # --- chase: take the next open, whatever it is
            e = bars[i + 1].open
            s = max(e - 1.5 * a, e * 0.92)
            chase = None
            if e > s:
                chase = resolve(bars, i + 1, e, s, None, horizon)
                chase.update(symbol=sym, date=bars[i + 1].date.isoformat(),
                             q=(bars[i + 1].date.month - 1) // 3 + 1)
                rows["chase"].append(chase)

            # --- retest: rest a limit at the level that was broken
            fill_at = None
            for j in range(i + 1, min(i + 1 + wait, len(bars))):
                if bars[j].low <= prior_high:
                    fill_at = j
                    break
            if fill_at is None:
                # Never came back. This is the cost of waiting, and it is only
                # visible by asking what the chase arm did with the same signal.
                if chase:
                    missed.append(chase)
                continue
            e2 = min(prior_high, bars[fill_at].open)
            s2 = max(e2 - 1.5 * a, e2 * 0.92)
            if e2 <= s2:
                continue
            o = resolve(bars, fill_at, e2, s2, None, horizon)
            o.update(symbol=sym, date=bars[fill_at].date.isoformat(),
                     q=(bars[fill_at].date.month - 1) // 3 + 1)
            rows["retest"].append(o)

    return {"signals": signals, "rows": rows, "missed": missed,
            "wait": wait, "horizon": horizon, "top": top, "year": year}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--wait", type=int, default=5,
                    help="sessions the retest limit rests before it is cancelled")
    ap.add_argument("--top", type=int, default=150)
    a = ap.parse_args()

    r = run(a.year, a.horizon, a.wait, a.top)
    print(f"\n=== {a.year}: {r['signals']} breakout signals, top {a.top} by "
          f"liquidity/day, {a.horizon}-day horizon, retest waits "
          f"{a.wait} sessions ===\n")
    print(f"{'entry':<10}{'taken':>7}{'fill%':>7}{'expect':>9}{'+/-SE':>8}"
          f"{'t':>6}{'totalR':>9}{'win%':>7}{'avgW':>7}{'avgL':>7}")
    for k in ("chase", "retest"):
        s = summarise(r["rows"][k])
        if not s["n"]:
            print(f"{k:<10}      0"); continue
        print(f"{k:<10}{s['n']:>7}{s['n']/r['signals']:>7.0%}"
              f"{s['expectancy']:>+9.3f}{s['se']:>8.3f}{s['t']:>+6.1f}"
              f"{s['total_R']:>+9.1f}{s['win_rate']:>7.0%}"
              f"{s['avg_win']:>+7.2f}{s['avg_loss']:>+7.2f}")

    m = summarise(r["missed"])
    print(f"\n--- what the retest arm FORGOES ---")
    if m["n"]:
        print(f"  {m['n']} signals never traded back to the level "
              f"({m['n']/r['signals']:.0%} of all signals).")
        print(f"  Chasing those same signals instead: expectancy "
              f"{m['expectancy']:+.3f}R, total {m['total_R']:+.1f}R, "
              f"win rate {m['win_rate']:.0%}, avg win {m['avg_win']:+.2f}")
        print(f"  Compare the chase arm overall above. If the forgone set is "
              f"BETTER than average,\n  waiting is selecting against its own "
              f"best outcomes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
