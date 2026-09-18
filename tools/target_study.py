#!/usr/bin/env python3
"""Forward-test target definitions: does the 1.5R gate select better trades?

D-24, open since 2026-09-18. Three ways to set a target, one gate:

  mechanical  entry + 3*ATR              >= 2.0R by construction; gate never binds
  structural  nearest overhead level     computed, not judged
  none        no target                  control: take every breakout, exit on time

The question is not which produces more trades. It is which produces better
ones, measured in R, forward, on real bars.

METHOD, stated because the assumptions are the result:

- Signal on close[i] > max(high[i-20:i]), the same test tools.screen uses.
- ENTRY at open[i+1]. You cannot buy the close you screened on. This also
  reproduces the gap that engine/sim.py's fill-at-next-open exposes, which is
  where the R gate actually binds.
- Stop = max(entry - 1.5*ATR, entry*0.92), the constitution's mandatory_stop.
- Everything that feeds a target is computed from bars[:i+1] only. A swing
  high must be CONFIRMED by bar i (its right-hand window has closed), or the
  study would be reading the future and every number would be a lie.
- Resolution walks bars i+1..i+H:
    * stop touched  -> fill at min(stop, that bar's open); a gap through the
                       stop is worse than -1R and pretending otherwise is the
                       single most flattering error a backtest can make
    * target touched-> fill at max(target, that bar's open)
    * both in one bar -> assume the STOP filled first; intraday order is
                       unknowable from daily bars and the conservative read is
                       the honest one
    * neither by H  -> exit at close[i+H], whatever R that is
- The 1.5 gate is applied to expected R at ENTRY, as engine/risk.py does.

Usage:
    python3 -m tools.target_study --year 2026 [--horizon 20] [--refresh]

Bars are cached; --refresh re-fetches.
"""
import argparse
import datetime as dt
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.alpaca import DryRunAlpaca
from adapters.base import AdapterError
from engine.market import Bar, atr
from tools.screen import load_universe, LOOKBACK, ATR_PERIOD

CACHE = Path(os.environ.get("TRADING_AGENT_CACHE",
             "/tmp/claude-0/target_study_bars.json"))
SWING_K = 3          # a pivot high must top its 3 bars either side
SWING_LOOKBACK = 120
MA_PERIOD = 200


# ---------------------------------------------------------------- levels
def round_step(price: float, coarse: bool = False) -> float:
    """The grid a trader actually watches.

    The fine grid (every dollar at $34) is not resistance, it is arithmetic.
    Measured 2026-09-18: it bound 68% of signals at a median 0.55R, which made
    "structural" mostly a round-number rule in disguise. The coarse grid keeps
    each step near 10-15% of price, which is the scale at which a round number
    is actually a level people defend.
    """
    if coarse:
        return 25.0 if price >= 100 else (10.0 if price >= 50 else
               (5.0 if price >= 20 else (1.0 if price >= 5 else 0.5)))
    return 5.0 if price >= 50 else (1.0 if price >= 10 else 0.5)


def overhead_levels(bars: List[Bar], i: int, entry: float,
                    coarse: bool = False) -> Dict[str, float]:
    """Resistance above `entry`, computed only from bars[:i+1].

    Three kinds, because they are the three a human actually looks at: where
    price last turned down, the long moving average everyone watches, and the
    next round number. All are rules. None is a judgement.
    """
    out: Dict[str, float] = {}

    # 1. nearest CONFIRMED swing high above entry. Confirmed means its
    #    right-hand window has closed by bar i — otherwise we are peeking.
    lo = max(SWING_K, i - SWING_LOOKBACK)
    cands = []
    for j in range(lo, i - SWING_K + 1):
        w = bars[j - SWING_K:j + SWING_K + 1]
        if bars[j].high >= max(b.high for b in w) and bars[j].high > entry:
            cands.append(bars[j].high)
    if cands:
        out["swing"] = min(cands)

    # 2. the 200-day average, if it is overhead
    if i + 1 >= MA_PERIOD:
        ma = sum(b.close for b in bars[i + 1 - MA_PERIOD:i + 1]) / MA_PERIOD
        if ma > entry:
            out["ma200"] = ma

    # 3. the next round number
    step = round_step(entry, coarse)
    rn = (int(entry / step) + 1) * step
    if rn > entry:
        out["round"] = rn
    return out


VARIANTS = {
    "structural":      (("swing", "ma200", "round"), False),
    "struct_coarse":   (("swing", "ma200", "round"), True),
    "struct_swing":    (("swing",), False),
    "struct_ma200":    (("ma200",), False),
}


def target_for(kind: str, bars: List[Bar], i: int, entry: float,
               a: float) -> Optional[float]:
    if kind == "mechanical":
        return entry + 3.0 * a
    if kind == "none":
        return None
    allowed, coarse = VARIANTS.get(kind, (("swing", "ma200", "round"), False))
    lv = {k: v for k, v in overhead_levels(bars, i, entry, coarse).items()
          if k in allowed}
    if not lv:
        # Nothing overhead within the window: the move is unobstructed, so the
        # mechanical target is the honest fallback rather than "no limit".
        return entry + 3.0 * a
    return min(lv.values())


# ---------------------------------------------------------------- outcome
def resolve(bars: List[Bar], entry_i: int, entry: float, stop: float,
            target: Optional[float], horizon: int) -> Dict:
    risk = entry - stop
    end = min(entry_i + horizon, len(bars) - 1)
    for k in range(entry_i, end + 1):
        b = bars[k]
        hit_stop = b.low <= stop
        hit_tgt = target is not None and b.high >= target
        if hit_stop:
            fill = min(stop, b.open)          # a gap opens below the stop
            return {"R": (fill - entry) / risk, "bars": k - entry_i,
                    "exit": "stop"}
        if hit_tgt:
            fill = max(target, b.open)
            return {"R": (fill - entry) / risk, "bars": k - entry_i,
                    "exit": "target"}
    return {"R": (bars[end].close - entry) / risk, "bars": end - entry_i,
            "exit": "timeout"}


# ---------------------------------------------------------------- data
def fetch(symbols: List[str], need: int, refresh: bool) -> Dict[str, List[Dict]]:
    if CACHE.exists() and not refresh:
        d = json.loads(CACHE.read_text())
        if d.get("need", 0) >= need and set(d["bars"]) >= set(symbols):
            print(f"using cached bars ({len(d['bars'])} symbols)")
            return d["bars"]
    a = DryRunAlpaca()
    out: Dict[str, List[Dict]] = {}
    for n, s in enumerate(symbols, 1):
        try:
            out[s] = a.bars(s, limit=need)
        except AdapterError:
            continue
        if n % 25 == 0:
            print(f"  fetched {n}/{len(symbols)}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"need": need, "bars": out}))
    print(f"fetched {len(out)} symbols, cached")
    return out


# ---------------------------------------------------------------- study
def run(year: int, horizon: int, min_r: float, refresh: bool) -> Dict:
    u = load_universe()
    syms = [r["symbol"] for r in u["symbols"]]
    need = 260 + MA_PERIOD + LOOKBACK + ATR_PERIOD + horizon + 20
    raw = fetch(syms, need, refresh)

    # structural_filter tests a different hypothesis from structural: use
    # overhead resistance to DECIDE WHETHER TO ENTER, then do not let it cap
    # the exit. Structure may be good at saying "this one is walled in" and
    # bad at saying "sell exactly here" — those are separable claims and the
    # first study conflated them.
    kinds = ["mechanical", "structural", "struct_coarse", "struct_swing",
             "struct_ma200", "structural_filter", "none"]
    trades: Dict[str, List[Dict]] = {k: [] for k in kinds}
    signals = 0

    for sym, rows in raw.items():
        bars = [Bar(dt.date.fromisoformat(r["date"]), r["open"], r["high"],
                    r["low"], r["close"], r["volume"]) for r in rows]
        if len(bars) < MA_PERIOD + LOOKBACK + ATR_PERIOD + 5:
            continue
        for i in range(MA_PERIOD, len(bars) - 1):
            if bars[i].date.year != year:
                continue
            prior = bars[i - LOOKBACK:i]
            if bars[i].close <= max(b.high for b in prior):
                continue
            a = atr(bars[:i + 1], ATR_PERIOD)
            if not a:
                continue
            entry = bars[i + 1].open
            stop = max(entry - 1.5 * a, entry * 0.92)
            if entry <= stop:
                continue
            signals += 1
            for kind in kinds:
                if kind == "structural_filter":
                    # gate on structure, then run with no target
                    gate_t = target_for("structural", bars, i, entry, a)
                    exp_r = (gate_t - entry) / (entry - stop) if gate_t else None
                    if exp_r is None or exp_r < min_r - 1e-9:
                        continue
                    t = None
                else:
                    t = target_for(kind, bars, i, entry, a)
                    exp_r = (t - entry) / (entry - stop) if t else None
                    taken = (kind == "none") or (exp_r is not None
                                                 and exp_r >= min_r - 1e-9)
                    if not taken:
                        continue
                o = resolve(bars, i + 1, entry, stop, t, horizon)
                trades[kind].append({
                    "symbol": sym, "date": bars[i + 1].date.isoformat(),
                    "q": (bars[i + 1].date.month - 1) // 3 + 1,
                    "expected_R": exp_r, **o})

    return {"year": year, "horizon": horizon, "min_r": min_r,
            "signals": signals, "trades": trades}


def summarise(rs: List[Dict]) -> Dict:
    if not rs:
        return {"n": 0}
    R = [t["R"] for t in rs]
    wins = [r for r in R if r > 0]
    sd = statistics.pstdev(R) if len(R) > 1 else 0.0
    se = sd / (len(R) ** 0.5) if R else 0.0
    return {"n": len(R), "expectancy": statistics.mean(R),
            "sd": sd, "se": se,
            "t": (statistics.mean(R) / se) if se else 0.0,
            "total_R": sum(R), "win_rate": len(wins) / len(R),
            "median_R": statistics.median(R),
            "avg_win": statistics.mean(wins) if wins else 0.0,
            "avg_loss": statistics.mean([r for r in R if r <= 0]) if len(wins) < len(R) else 0.0,
            "best": max(R), "worst": min(R),
            "hold": statistics.mean([t["bars"] for t in rs]),
            "exits": {e: sum(1 for t in rs if t["exit"] == e)
                      for e in ("target", "stop", "timeout")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--min-r", type=float, default=1.5)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    r = run(a.year, a.horizon, a.min_r, a.refresh)
    print(f"\n=== {a.year}: {r['signals']} breakout signals, "
          f"{a.horizon}-day horizon, gate at {a.min_r:.1f}R ===\n")
    print(f"{'target':<18}{'taken':>7}{'%sig':>7}{'expect':>9}{'+/-SE':>8}{'t':>6}{'totalR':>9}"
          f"{'win%':>7}{'avgW':>7}{'avgL':>7}{'hold':>6}   exits")
    for kind in ("mechanical", "structural", "struct_coarse", "struct_swing", "struct_ma200", "structural_filter", "none"):
        s = summarise(r["trades"][kind])
        if not s["n"]:
            print(f"{kind:<18}       0")
            continue
        e = s["exits"]
        print(f"{kind:<18}{s['n']:>7}{s['n']/r['signals']:>7.0%}"
              f"{s['expectancy']:>+9.3f}{s['se']:>8.3f}{s['t']:>+6.1f}"
              f"{s['total_R']:>+9.1f}"
              f"{s['win_rate']:>7.0%}{s['avg_win']:>+7.2f}{s['avg_loss']:>+7.2f}"
              f"{s['hold']:>6.1f}   T{e['target']} S{e['stop']} O{e['timeout']}")

    print(f"\n--- by quarter (expectancy in R, n) ---")
    print(f"{'target':<18}" + "".join(f"{'Q'+str(q):>16}" for q in (1, 2, 3, 4)))
    for kind in ("mechanical", "structural", "struct_coarse", "struct_swing", "struct_ma200", "structural_filter", "none"):
        row = f"{kind:<18}"
        for q in (1, 2, 3, 4):
            s = summarise([t for t in r["trades"][kind] if t["q"] == q])
            row += f"{'—':>16}" if not s["n"] else f"{s['expectancy']:>+10.3f} ({s['n']:>3})"
        print(row)

    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2, default=str))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
