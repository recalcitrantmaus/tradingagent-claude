#!/usr/bin/env python3
"""The universe and the breakout screen, as code instead of a claim.

Two sessions set posture partly on "zero of N names are above their 20-day
high". That number decided what not to trade and it was not re-runnable from
the repository — a screen that vetoes trades has to be auditable, or it is
just an assertion with a number in it.

    python3 -m tools.screen --build-universe   # refresh data/universe.json
    python3 -m tools.screen                    # today's breakouts
    python3 -m tools.screen --base-rate 90     # how often does this fire?

The universe is committed as data, not rebuilt per run. A screen whose inputs
change silently underneath it cannot be audited either, and "today's universe"
must mean the same thing when someone re-reads the decision next week.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.alpaca import AlpacaAdapter, DryRunAlpaca, DATA, PAPER_TRADING
from adapters.base import AdapterError
from engine.market import Bar, atr

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_FILE = ROOT / "data" / "universe.json"

# --- universe criteria. Every one of these is a decision, so each is named. ---
CRITERIA = {
    # Affordability. At $300 with whole-share sizing the engine cannot buy one
    # share above roughly $75, so anything dearer is noise in the screen. This
    # is the number to revisit if fractional sizing is ever enabled.
    "max_price": 75.0,
    # Junk floor. Sub-$3 names are where spreads, reverse splits and promotion
    # schemes live. At $300 a 5% spread is a whole trade's edge.
    "min_price": 3.0,
    # Liquidity, stated in IEX dollar volume — NOT consolidated. The free
    # Alpaca feed reports only IEX's own prints, which on 2026-09-17 measured
    # roughly 4% of consolidated tape: Ford showed 1.7M shares on IEX against
    # 45.8M on Yahoo. A "$25M" floor applied to this field therefore demands
    # about $600M of real volume and passed 14 names out of 11,833. The floor
    # below is ~$1.5M IEX, standing in for roughly $35M consolidated at that
    # ratio. The ratio is not constant across names, so this is a coarse
    # filter and is treated as one: it is for excluding the illiquid, not for
    # ranking the liquid.
    #
    # Liquidity still matters more than usual here. Alpaca's most-actives list
    # is dominated by low-float microcaps pumping on volume, so volume alone
    # selects FOR the thing a $300 account must avoid; the price floor is what
    # actually filters those out.
    "min_dollar_volume": 1_500_000.0,
    # OTC has no consolidated tape worth trusting at this size.
    "exchanges": ["NYSE", "NASDAQ", "AMEX", "BATS", "ARCA"],
    # Leveraged and inverse products decay and do not mean-revert like equity.
    "exclude_name_contains": ["2X", "3X", "-1X", "ULTRA", "ULTRASHORT",
                              "INVERSE", "LEVERAGED", "BULL 2", "BEAR 2"],
    "size": 150,
}

# --- screen parameters ---
LOOKBACK = 20          # the breakout window, in sessions
ATR_PERIOD = 14


def _bars(rows: List[Dict]) -> List[Bar]:
    return [Bar(dt.date.fromisoformat(r["date"]), r["open"], r["high"],
                r["low"], r["close"], r["volume"]) for r in rows]


def build_universe(adapter, criteria: Dict = None) -> Dict:
    """Assemble the universe from Alpaca's asset list plus live snapshots."""
    c = dict(CRITERIA, **(criteria or {}))
    assets = adapter._request(
        "GET", f"{PAPER_TRADING}/v2/assets?status=active&asset_class=us_equity")
    cand = [a for a in assets
            if a.get("tradable")
            and a.get("exchange") in c["exchanges"]
            and not any(x in (a.get("name") or "").upper()
                        for x in c["exclude_name_contains"])]
    syms = [a["symbol"] for a in cand if "." not in a["symbol"]
            and "/" not in a["symbol"]]
    print(f"{len(assets)} active -> {len(syms)} after exchange/name filters")

    rows, batch = [], 500
    for i in range(0, len(syms), batch):
        chunk = syms[i:i + batch]
        try:
            snaps = adapter._request(
                "GET", f"{DATA}/v2/stocks/snapshots?symbols={','.join(chunk)}")
        except AdapterError as e:
            print(f"  snapshot batch {i//batch} failed: {str(e)[:70]}")
            continue
        for sym, s in (snaps or {}).items():
            bar = (s or {}).get("dailyBar") or {}
            px, vol = bar.get("c"), bar.get("v")
            if not px or not vol:
                continue
            dv = px * vol
            if c["min_price"] <= px <= c["max_price"] and dv >= c["min_dollar_volume"]:
                rows.append({"symbol": sym, "price": round(px, 2),
                             "dollar_volume": round(dv)})
        print(f"  priced {i + len(chunk)}/{len(syms)}: {len(rows)} pass so far")

    rows.sort(key=lambda r: -r["dollar_volume"])
    rows = rows[:c["size"]]
    return {"built": dt.date.today().isoformat(), "criteria": c,
            "count": len(rows), "symbols": rows}


def load_universe() -> Dict:
    if not UNIVERSE_FILE.exists():
        raise SystemExit(
            f"no {UNIVERSE_FILE}. Run: python3 -m tools.screen --build-universe")
    return json.loads(UNIVERSE_FILE.read_text())


def breakout_at(bars: List[Bar], i: int, lookback: int = LOOKBACK) -> Optional[Dict]:
    """Did bar i close above the prior `lookback` sessions' high?"""
    if i < lookback or i >= len(bars):
        return None
    prior = bars[i - lookback:i]
    ph = max(b.high for b in prior)
    a = atr(bars[:i + 1], ATR_PERIOD)
    if not a or bars[i].close <= ph:
        return None
    return {"close": bars[i].close, "prior_high": ph, "atr": a,
            "pct_over": (bars[i].close / ph - 1) * 100}


def screen(adapter, symbols: List[str], limit: int = 90) -> Dict:
    hits, scanned, nodata = [], 0, []
    for sym in symbols:
        try:
            bars = _bars(adapter.bars(sym, limit=limit))
        except AdapterError:
            nodata.append(sym)
            continue
        if len(bars) < LOOKBACK + ATR_PERIOD:
            nodata.append(sym)
            continue
        scanned += 1
        b = breakout_at(bars, len(bars) - 1)
        if b:
            hits.append(dict(symbol=sym, **b))
    return {"scanned": scanned, "no_data": nodata, "hits": hits}


def base_rate(adapter, symbols: List[str], sessions: int) -> Dict:
    """How often does this screen fire at all?

    The question two empty sessions raised: is the screen finding nothing
    because the tape is quiet, or because a 20-day breakout in an affordable,
    liquid universe is a rare event and this strategy is structurally
    incompatible with the account? One is patience. The other is a design
    fault, and they are indistinguishable from inside a single quiet week.
    """
    need = sessions + LOOKBACK + ATR_PERIOD + 5
    per_day: Dict[str, int] = {}
    per_symbol: Dict[str, int] = {}
    scanned = 0
    for sym in symbols:
        try:
            bars = _bars(adapter.bars(sym, limit=need))
        except AdapterError:
            continue
        if len(bars) < LOOKBACK + ATR_PERIOD + 2:
            continue
        scanned += 1
        start = max(LOOKBACK + ATR_PERIOD, len(bars) - sessions)
        for i in range(start, len(bars)):
            if breakout_at(bars, i):
                d = bars[i].date.isoformat()
                per_day[d] = per_day.get(d, 0) + 1
                per_symbol[sym] = per_symbol.get(sym, 0) + 1
    days = sorted(per_day)
    fired = len(days)
    window = min(sessions, fired if fired else sessions)
    return {"symbols_scanned": scanned, "sessions_requested": sessions,
            "days_with_at_least_one": fired,
            "total_signals": sum(per_day.values()),
            "per_day": per_day, "per_symbol": per_symbol,
            "busiest": sorted(per_day.items(), key=lambda kv: -kv[1])[:5]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-universe", action="store_true")
    ap.add_argument("--base-rate", type=int, metavar="SESSIONS")
    ap.add_argument("--max-price", type=float)
    ap.add_argument("--size", type=int)
    a = ap.parse_args()

    adapter = DryRunAlpaca()

    if a.build_universe:
        crit = {}
        if a.max_price:
            crit["max_price"] = a.max_price
        if a.size:
            crit["size"] = a.size
        u = build_universe(adapter, crit)
        UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UNIVERSE_FILE.write_text(json.dumps(u, indent=2))
        print(f"\nwrote {UNIVERSE_FILE}: {u['count']} symbols, "
              f"${u['criteria']['min_price']:.0f}-${u['criteria']['max_price']:.0f}, "
              f"min ${u['criteria']['min_dollar_volume']/1e6:.0f}M dollar volume")
        return 0

    u = load_universe()
    syms = [r["symbol"] for r in u["symbols"]]
    print(f"universe: {len(syms)} symbols, built {u['built']}")

    if a.base_rate:
        r = base_rate(adapter, syms, a.base_rate)
        n = r["sessions_requested"]
        print(f"\nscanned {r['symbols_scanned']} symbols over ~{n} sessions")
        print(f"days with at least one breakout: {r['days_with_at_least_one']}")
        print(f"total signals: {r['total_signals']}")
        if r["days_with_at_least_one"]:
            print(f"signals per firing day: "
                  f"{r['total_signals']/r['days_with_at_least_one']:.1f}")
            print(f"busiest days: {r['busiest']}")
        return 0

    r = screen(adapter, syms)
    print(f"scanned {r['scanned']}, no usable history for {len(r['no_data'])}")
    if not r["hits"]:
        print("\nno breakouts today.")
        return 0
    print(f"\n{len(r['hits'])} breakout(s):")
    for h in sorted(r["hits"], key=lambda x: -x["pct_over"]):
        print(f"  {h['symbol']:6} {h['close']:>8.2f}  over {h['prior_high']:>8.2f} "
              f"({h['pct_over']:+.2f}%)  ATR {h['atr']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
