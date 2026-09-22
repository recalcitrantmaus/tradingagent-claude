#!/usr/bin/env python3
"""Point-in-time version of the target study: no survivorship in the universe.

`tools/target_study.py` screened a universe built from prices as of
2026-09-17, then backtested January. A stock that was $40 in January and $200
today was excluded from its own January signals — and for a breakout strategy
those are the trades that matter most, so the right tail was truncated exactly
where the edge lives.

This rebuilds eligibility AT EACH SIGNAL DATE from the full tradable list
(13,169 names), not from a snapshot of today:

    eligible(sym, i)  <=>  3 <= close[i] <= 75
                      and  median 20-day dollar volume up to i >= floor
                      and  exchange and name filters (static, not price-based)

A name is therefore in the universe on the days it actually qualified and out
on the days it did not, which is the same test the live screen applies each
morning.

What this still does not fix: names delisted or removed from /v2/assets
entirely are absent, which biases the other way (upward). Both biases are now
named; only one of them has been removed.

    python3 -m tools.pit_study --fetch          # ~500 requests, then cached
    python3 -m tools.pit_study --year 2026
    python3 -m tools.pit_study --year 2026 --inverse   # inverse/short ETFs only
"""
import argparse
import datetime as dt
import gzip
import json
import statistics
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.alpaca import AlpacaAdapter, DATA
from adapters.base import AdapterError
from engine.market import Bar, atr
from tools.screen import LOOKBACK, ATR_PERIOD
from tools.target_study import target_for, resolve, summarise, MA_PERIOD

CACHE = Path("/tmp/claude-0/pit_bars.json.gz")
EXCHANGES = ("NYSE", "NASDAQ", "AMEX", "BATS", "ARCA")
LEVERAGED = ("2X", "3X", "-1X", "ULTRA", "ULTRASHORT", "LEVERAGED",
             "BULL 2", "BEAR 2")
# Un-leveraged inverse funds are a different animal from 2x/3x: they reset
# daily too, but without the leverage multiplier the decay is an order of
# magnitude smaller. They are the only downside vehicle that fits every
# existing rule — long, whole-share, and able to carry an atomic bracket.
INVERSE_HINTS = ("INVERSE", "SHORT ", "BEAR")
MIN_PX, MAX_PX = 3.0, 75.0
MIN_DV = 1_500_000.0          # IEX dollar volume, ~4% of consolidated
# The IEX feed on this plan begins 2020-07-27; asking for anything earlier
# just returns that. Taking all of it gives 2021-2026 as study years once the
# 200-day MA lookback is paid, which is the only way to get an out-of-sample
# test: every result so far is a single year at t between 1.1 and 1.7.
START = "2020-07-01"
PRUNE_FROM = 2021             # keep a symbol if it qualified in ANY study year


def asset_list(a: AlpacaAdapter) -> Dict[str, str]:
    rows = a._request("GET", f"{a.base}/v2/assets?status=active&asset_class=us_equity")
    return {r["symbol"]: (r.get("name") or "").upper()
            for r in rows
            if r.get("tradable") and r.get("exchange") in EXCHANGES
            and "/" not in r["symbol"]}


def classify(name: str) -> str:
    up = name.upper()
    if any(k in up for k in LEVERAGED):
        return "leveraged"
    if any(k in up for k in INVERSE_HINTS):
        return "inverse"
    return "plain"


def fetch_all(batch: int = 200) -> None:
    a = AlpacaAdapter(live=False)
    names = asset_list(a)
    syms = sorted(names)
    print(f"{len(syms)} tradable symbols; fetching daily bars from {START}")
    kept: Dict[str, List] = {}
    failed: List[int] = []
    for n in range(0, len(syms), batch):
        chunk = syms[n:n + batch]
        got: Dict[str, List] = {}
        token = None
        complete = False
        # A page failure used to `break` and cache whatever had arrived, which
        # over 31 pages per batch means one hiccup silently truncates 200
        # symbols' history into something that still parses as a valid series.
        # Retry the page; if it will not come, drop the whole batch loudly
        # rather than cache a shortened one.
        for _ in range(200):
            q = {"symbols": ",".join(chunk), "timeframe": "1Day",
                 "start": START, "limit": 10000, "adjustment": "split",
                 "feed": "iex"}
            if token:
                q["page_token"] = token
            for attempt in range(4):
                try:
                    d = a._request("GET", f"{DATA}/v2/stocks/bars?"
                                          f"{urllib.parse.urlencode(q)}")
                    break
                except AdapterError as e:
                    err = str(e)[:120]
                    time.sleep(2 ** attempt)
            else:
                print(f"  batch {n} DROPPED after 4 retries: {err}")
                failed.append(n)
                break
            for s, rows in (d.get("bars") or {}).items():
                got.setdefault(s, []).extend(rows)
            token = d.get("next_page_token")
            if not token:
                complete = True
                break
        if not complete:
            if n not in failed:
                print(f"  batch {n} DROPPED: page cap hit, history truncated")
                failed.append(n)
            continue
        # Prune during the fetch: a symbol is worth caching only if it was
        # ever plausibly tradable by this account. Keeps the cache ~50MB
        # instead of ~400MB.
        for s, rows in got.items():
            # Per YEAR, not over the whole window: a name that was liquid for
            # one month in 2021 and dead since should not be cached, but a
            # name that qualified in any single study year should be. The
            # 2026-only test this replaces would have silently deleted every
            # symbol that mattered in 2022 and was gone by now.
            per_year: Dict[int, int] = {}
            for b in rows:
                if MIN_PX <= b["c"] <= MAX_PX and b["c"] * b["v"] >= MIN_DV:
                    y = int(b["t"][:4])
                    if y >= PRUNE_FROM:
                        per_year[y] = per_year.get(y, 0) + 1
            if per_year and max(per_year.values()) >= 20:
                kept[s] = [[b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"]]
                           for b in rows]
        print(f"  {n + len(chunk):>6}/{len(syms)}  kept {len(kept)}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wt") as fh:
        json.dump({"names": {s: names.get(s, "") for s in kept},
                   "bars": kept}, fh)
    print(f"cached {len(kept)} symbols -> {CACHE} "
          f"({CACHE.stat().st_size / 1e6:.0f} MB)")
    if failed:
        print(f"WARNING: {len(failed)} batches dropped at offsets {failed} — "
              f"those symbols are absent, not truncated. Re-run --fetch.")


def eligible(bars: List[Bar], i: int) -> bool:
    """Would the live screen have had this name in its universe on day i?"""
    px = bars[i].close
    if not (MIN_PX <= px <= MAX_PX):
        return False
    w = bars[max(0, i - 19):i + 1]
    return statistics.median([b.close * b.volume for b in w]) >= MIN_DV


def liquidity_ranked_membership(raw, names, want, year, top: int):
    """Which symbols were in the top-`top` by liquidity ON EACH DATE.

    The 150-name universe this replaces was not merely "eligible" — it was
    `size: 150`, the most liquid eligible names, ranked. Comparing an
    unranked 1,563-name point-in-time set against it therefore changes TWO
    things at once: it removes survivorship AND it drops the liquidity cap.
    This isolates the second so the two can be told apart.
    """
    per_date: Dict[str, List] = {}
    for sym, rows in raw.items():
        if classify(names.get(sym, "")) != want:
            continue
        closes = [r[4] for r in rows]
        vols = [r[4] * r[5] for r in rows]
        for i, r in enumerate(rows):
            if r[0][:4] != str(year):
                continue
            if not (MIN_PX <= closes[i] <= MAX_PX):
                continue
            w = vols[max(0, i - 19):i + 1]
            dv = statistics.median(w)
            if dv < MIN_DV:
                continue
            per_date.setdefault(r[0], []).append((dv, sym))
    return {d: {s for _, s in sorted(v, reverse=True)[:top]}
            for d, v in per_date.items()}


def run(year: int, horizon: int, min_r: float, want: str, top: int = 0,
        blob=None) -> Dict:
    if blob is None:
        with gzip.open(CACHE, "rt") as fh:
            blob = json.load(fh)
    names, raw = blob["names"], blob["bars"]
    member = (liquidity_ranked_membership(raw, names, want, year, top)
              if top else None)
    kinds = ["mechanical", "struct_swing", "struct_coarse", "none"]
    trades = {k: [] for k in kinds}
    signals, universe_days, syms_used = 0, 0, set()

    for sym, rows in raw.items():
        cls = classify(names.get(sym, ""))
        if want == "plain" and cls != "plain":
            continue
        if want == "inverse" and cls != "inverse":
            continue
        bars = [Bar(dt.date.fromisoformat(r[0]), r[1], r[2], r[3], r[4], r[5])
                for r in rows]
        if len(bars) < MA_PERIOD + LOOKBACK + ATR_PERIOD + 5:
            continue
        for i in range(MA_PERIOD, len(bars) - 1):
            if bars[i].date.year != year or not eligible(bars, i):
                continue
            if member is not None and sym not in member.get(
                    bars[i].date.isoformat(), ()):
                continue
            universe_days += 1
            syms_used.add(sym)
            if bars[i].close <= max(b.high for b in bars[i - LOOKBACK:i]):
                continue
            a_ = atr(bars[:i + 1], ATR_PERIOD)
            if not a_:
                continue
            entry = bars[i + 1].open
            stop = max(entry - 1.5 * a_, entry * 0.92)
            if entry <= stop:
                continue
            signals += 1
            for kind in kinds:
                t = target_for(kind, bars, i, entry, a_)
                exp_r = (t - entry) / (entry - stop) if t else None
                if kind != "none" and (exp_r is None or exp_r < min_r - 1e-9):
                    continue
                o = resolve(bars, i + 1, entry, stop, t, horizon)
                trades[kind].append({
                    "symbol": sym, "date": bars[i + 1].date.isoformat(),
                    "q": (bars[i + 1].date.month - 1) // 3 + 1,
                    "expected_R": exp_r, **o})
    return {"year": year, "horizon": horizon, "signals": signals,
            "symbols": len(syms_used), "universe_days": universe_days,
            "trades": trades, "kinds": kinds}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--min-r", type=float, default=1.5)
    ap.add_argument("--inverse", action="store_true")
    ap.add_argument("--top", type=int, default=0,
                    help="keep only the N most liquid eligible names PER DAY, "
                         "matching the old universe's size cap")
    a = ap.parse_args()
    if a.fetch:
        fetch_all()
        return 0
    if not CACHE.exists():
        print("no cache; run --fetch first", file=sys.stderr)
        return 2

    r = run(a.year, a.horizon, a.min_r,
            "inverse" if a.inverse else "plain", a.top)
    label = "INVERSE / SHORT ETFs" if a.inverse else "point-in-time universe"
    if a.top:
        label += f", top {a.top} by liquidity per day"
    print(f"\n=== {a.year}, {label} ===")
    print(f"{r['symbols']} symbols qualified at some point; "
          f"{r['universe_days']:,} symbol-days in the universe; "
          f"{r['signals']} breakout signals; {a.horizon}-day horizon\n")
    print(f"{'target':<16}{'taken':>7}{'expect':>9}{'+/-SE':>8}{'t':>6}"
          f"{'totalR':>9}{'win%':>7}{'avgW':>7}{'avgL':>7}   exits")
    for kind in r["kinds"]:
        s = summarise(r["trades"][kind])
        if not s["n"]:
            print(f"{kind:<16}      0")
            continue
        e = s["exits"]
        print(f"{kind:<16}{s['n']:>7}{s['expectancy']:>+9.3f}{s['se']:>8.3f}"
              f"{s['t']:>+6.1f}{s['total_R']:>+9.1f}{s['win_rate']:>7.0%}"
              f"{s['avg_win']:>+7.2f}{s['avg_loss']:>+7.2f}   "
              f"T{e['target']} S{e['stop']} O{e['timeout']}")
    print(f"\n--- by quarter (expectancy, n) ---")
    for kind in r["kinds"]:
        row = f"{kind:<16}"
        for q in (1, 2, 3, 4):
            s = summarise([t for t in r["trades"][kind] if t["q"] == q])
            row += f"{'—':>16}" if not s["n"] else f"{s['expectancy']:>+10.3f} ({s['n']:>4})"
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
