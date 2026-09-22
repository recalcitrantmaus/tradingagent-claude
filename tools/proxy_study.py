#!/usr/bin/env python3
"""Is there a SIGNAL-TIME proxy for "this breakout will not pull back"?

docs/16-entry-study.md found the retest entry ahead on 2026 data, and found
something larger sitting next to it: the 483 signals (26%) that never traded
back to the broken level return **+1.054R** when chased, against +0.054R for
chasing everything. That sub-population is where the money is, and the retest
rule is absent from all of it.

Collecting it requires deciding at SIGNAL TIME, which the entry study cannot
do — its +508.9R is a hindsight number. So: can anything visible on the signal
bar separate the 483 from the 1,398?

Every feature here is computed from bars[:i+1] only. Nothing looks forward.

    python3 -m tools.proxy_study --year 2026 --top 150 --wait 5
"""
import argparse
import datetime as dt
import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.market import Bar, atr
from tools.screen import LOOKBACK, ATR_PERIOD
from tools.pit_study import (CACHE, MA_PERIOD, classify, eligible,
                             liquidity_ranked_membership)
from tools.target_study import resolve

FEATURES = {
    "breakout_%": "how far the close cleared the prior 20-day high",
    "gap_%": "next open against the signal close — the chase price",
    "rel_volume": "signal-day volume / 20-day median",
    "dist_50ma_%": "close above its 50-day average",
    "dist_200ma_%": "close above its 200-day average",
    "atr_%": "ATR(14) as a share of price — the name's own volatility",
}


def run(year: int, wait: int, top: int, horizon: int, blob=None) -> List[Dict]:
    blob = blob if blob is not None else json.load(gzip.open(CACHE, "rt"))
    names, raw = blob["names"], blob["bars"]
    member = liquidity_ranked_membership(raw, names, "plain", year, top) if top else None
    out: List[Dict] = []

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
            ph = max(x.high for x in bars[i - LOOKBACK:i])
            if b.close <= ph:
                continue
            a = atr(bars[:i + 1], ATR_PERIOD)
            if not a or b.close <= 0:
                continue

            ma50 = sum(x.close for x in bars[i - 49:i + 1]) / 50
            ma200 = sum(x.close for x in bars[i - 199:i + 1]) / 200
            vols = [x.volume for x in bars[i - 19:i]]
            medv = statistics.median(vols) if vols else 0

            # forward label — used ONLY as the outcome, never as a feature
            pulled_back = any(bars[j].low <= ph
                              for j in range(i + 1, min(i + 1 + wait, len(bars))))
            e = bars[i + 1].open
            s = max(e - 1.5 * a, e * 0.92)
            if e <= s:
                continue
            chase_R = resolve(bars, i + 1, e, s, None, horizon)["R"]

            out.append({
                "breakout_%": (b.close - ph) / ph * 100,
                "gap_%": (e - b.close) / b.close * 100,
                "rel_volume": (b.volume / medv) if medv else 0.0,
                "dist_50ma_%": (b.close - ma50) / b.close * 100,
                "dist_200ma_%": (b.close - ma200) / b.close * 100,
                "atr_%": a / b.close * 100,
                "no_pullback": 0 if pulled_back else 1,
                "chase_R": chase_R,
            })
    return out


def quintiles(rows: List[Dict], feat: str) -> None:
    rows = sorted(rows, key=lambda r: r[feat])
    n = len(rows) // 5
    base_np = sum(r["no_pullback"] for r in rows) / len(rows)
    base_R = statistics.mean(r["chase_R"] for r in rows)
    print(f"\n  {feat}  — {FEATURES[feat]}")
    print(f"    {'quintile':<12}{'range':>22}{'n':>6}{'no-pullback%':>14}"
          f"{'chase R':>10}")
    for q in range(5):
        part = rows[q * n:(q + 1) * n] if q < 4 else rows[4 * n:]
        if not part:
            continue
        np_ = sum(r["no_pullback"] for r in part) / len(part)
        mr = statistics.mean(r["chase_R"] for r in part)
        rng = f"{part[0][feat]:.2f} .. {part[-1][feat]:.2f}"
        flag = ""
        if np_ > base_np * 1.25:
            flag = "  <-- richer in no-pullbacks"
        print(f"    Q{q+1:<11}{rng:>22}{len(part):>6}{np_:>13.0%}{mr:>+10.3f}{flag}")
    print(f"    {'(baseline)':<12}{'':>22}{len(rows):>6}{base_np:>13.0%}{base_R:>+10.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--wait", type=int, default=5)
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--horizon", type=int, default=20)
    a = ap.parse_args()

    rows = run(a.year, a.wait, a.top, a.horizon)
    npb = sum(r["no_pullback"] for r in rows)
    print(f"\n=== {a.year}: {len(rows)} signals, {npb} ({npb/len(rows):.0%}) never "
          f"pulled back within {a.wait} sessions ===")
    print("A feature is useful only if a quintile is BOTH richer in "
          "no-pullbacks AND better in chase R.")
    for f in FEATURES:
        quintiles(rows, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
