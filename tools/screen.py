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
import statistics
import sys
from collections import Counter
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
            # prevDailyBar, NOT dailyBar (M-29, fixed 2026-09-22).
            #
            # `dailyBar` is TODAY, and during the session it is a PARTIAL bar.
            # Building the universe at 09:50 ET therefore measured twenty
            # minutes of volume against a full-day floor, so a $1.5M threshold
            # behaved like roughly $30M/day and excluded names that are
            # plainly liquid: MARA, CMCSA, MNST, ZTS and TFC were all dropped
            # on 2026-09-22 for not having printed $1.5M *yet*. Measured again
            # at 11:58 ET the same day, today's dollar volume ran 0.25x to
            # 1.46x of the prior completed session across ten names — so the
            # threshold was not a threshold, it was a function of the clock.
            #
            # Worse than being wrong, it was not REPRODUCIBLE: the scan walks
            # ~11,800 assets over several minutes, so the effective floor
            # moved *during a single build*. KR was excluded while the build
            # ran and passed minutes later. The docstring at the top of this
            # file promises a universe that "must mean the same thing when
            # someone re-reads the decision next week"; with a partial bar it
            # did not mean the same thing an hour later.
            #
            # prevDailyBar is a completed session. It is identical at 09:31
            # and at 15:59, which is what makes the build auditable. It is
            # still IEX volume, so the ~4% calibration documented in CRITERIA
            # remains exactly right — measured at 3.8% median on 2026-09-22.
            bar = (s or {}).get("prevDailyBar") or {}
            px, vol = bar.get("c"), bar.get("v")
            if not px or not vol:
                continue
            dv = px * vol
            if c["min_price"] <= px <= c["max_price"] and dv >= c["min_dollar_volume"]:
                rows.append({"symbol": sym, "price": round(px, 2),
                             "dollar_volume": round(dv),
                             "session": (bar.get("t") or "")[:10]})
        print(f"  priced {i + len(chunk)}/{len(syms)}: {len(rows)} pass so far")

    rows.sort(key=lambda r: -r["dollar_volume"])
    rows = rows[:c["size"]]

    # Which session the liquidity figures describe — taken from the names that
    # actually MADE the universe, as the most common value among them.
    #
    # The first version of this line read the first symbol the API happened to
    # return, and two consecutive builds reported 2026-09-14 and 2026-09-21
    # while selecting identical universes: a name that had not traded in a
    # week carries a week-old prevDailyBar, and it was labelling the whole
    # file. Caught by the reproducibility check written for M-29, which is the
    # only reason it is not still there. A provenance field that is wrong is
    # worse than no provenance field, because it is believed.
    sessions = Counter(r["session"] for r in rows if r["session"])
    dominant = sessions.most_common(1)[0][0] if sessions else "unknown"
    stale = sorted({s for s in sessions if s != dominant})

    return {"built": dt.date.today().isoformat(), "criteria": c,
            "liquidity_session": dominant,
            # Not every name trades every session. Naming the exceptions beats
            # implying a uniformity that is not there.
            "other_sessions_present": stale,
            "volume_feed": "iex (prevDailyBar, completed session)",
            "count": len(rows), "symbols": rows}


def load_universe() -> Dict:
    if not UNIVERSE_FILE.exists():
        raise SystemExit(
            f"no {UNIVERSE_FILE}. Run: python3 -m tools.screen --build-universe")
    return json.loads(UNIVERSE_FILE.read_text())


def completed(bars: List[Bar], today: Optional[dt.date] = None) -> List[Bar]:
    """Drop the current session's bar.

    Needed since bars moved to SIP (M-30): today's bar is both incomplete and
    15 minutes stale, so it is not a price and not a session. Levels and ATR
    come from here; the price comes from `adapter.last_trade()`.
    """
    today = today or dt.date.today()
    return [b for b in bars if b.date < today]


def breakout_at(bars: List[Bar], i: int, lookback: int = LOOKBACK) -> Optional[Dict]:
    """Did bar i close above the prior `lookback` sessions' high?

    For HISTORY — base rates and replays, where bar i is a completed session
    and its close is the real close. For a live decision use `breakout_now`,
    which takes the price from a real-time source instead of from a bar.
    """
    if i < lookback or i >= len(bars):
        return None
    return breakout_now(bars[:i + 1], bars[i].close, lookback, _self=True)


def breakout_now(hist: List[Bar], price: float,
                 lookback: int = LOOKBACK, _self: bool = False) -> Optional[Dict]:
    """Is `price` above the prior `lookback` COMPLETED sessions' high?

    The level and the price come from different places on purpose. The level
    is an extremum over completed sessions and must be consolidated (SIP), or
    it is understated and the breakout is a phantom — M-30, measured at 1 in
    59 names. The price must be real-time, because SIP is 15 minutes delayed
    and a stale price is a stale entry.
    """
    window = hist[:-1] if _self else hist
    if len(window) < lookback:
        return None
    prior = window[-lookback:]
    ph = max(b.high for b in prior)
    a = atr(hist, ATR_PERIOD)
    if not a or price <= ph:
        return None
    return {"close": price, "prior_high": ph, "atr": a,
            "pct_over": (price / ph - 1) * 100}


def screen(adapter, symbols: List[str], limit: int = 90) -> Dict:
    hits, scanned, nodata = [], 0, []
    for sym in symbols:
        try:
            bars = _bars(adapter.bars(sym, limit=limit))
        except AdapterError:
            nodata.append(sym)
            continue
        hist = completed(bars)
        if len(hist) < LOOKBACK + ATR_PERIOD:
            nodata.append(sym)
            continue
        # The price NOW, not the last bar's close: bars are SIP and a quarter
        # of an hour old. A missing price stands the symbol down rather than
        # falling back to the stale series.
        px = adapter.last_trade(sym)
        if px is None:
            nodata.append(sym)
            continue
        scanned += 1
        b = breakout_now(hist, px)
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



def replay(adapter, symbols: List[str], sessions: int, equity: float) -> Dict:
    """Of the breakouts the screen finds, how many could this account TAKE?

    base_rate() answers whether the strategy fires. This answers the question
    that actually decides whether the strategy is usable at $300: whether a
    signal survives whole-share rounding, the 25% single-position cap, the 2%
    risk budget and the cash reserve.

    It pushes each historical signal through `RiskOfficer.evaluate` itself
    rather than restating the arithmetic, so the answer cannot drift away from
    the engine when the engine changes. The proposal shape is the mechanical
    one (`target = close + 3*ATR` against `stop = max(close - 1.5*ATR,
    close*0.92)`), which is the shape `paper_session.propose_mechanical`
    builds. Note what that implies for the expected-R gate: 3*ATR against at
    most 1.5*ATR is 2.0R by construction, so a mechanical proposal can never
    fail it. A plan that sets a STRUCTURAL target — the next real resistance —
    is a different distribution entirely, and this replay says nothing about it.
    """
    import datetime as _dt
    from engine.config import DEFAULT as _CFG
    from engine.portfolio import Portfolio as _PF
    from engine.risk import RiskOfficer as _RO, OrderProposal as _OP

    need = sessions + LOOKBACK + ATR_PERIOD + 5
    signals = []
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
            if not breakout_at(bars, i):
                continue
            a = atr(bars[max(0, i - ATR_PERIOD - 1):i + 1], ATR_PERIOD)
            if not a:
                continue
            px = bars[i].close
            signals.append({"symbol": sym, "date": bars[i].date.isoformat(),
                            "price": px, "atr": a,
                            "stop": max(px - 1.5 * a, px * 0.92),
                            "target": px + 3.0 * a})

    ro = _RO(_CFG)
    today = _dt.date.today()
    ro.start_day(today, equity)
    approved, rejects, days = [], {}, {}
    for s in signals:
        pf = _PF(equity)
        pf.cash = equity
        d = ro.evaluate(_OP(symbol=s["symbol"], asset_class="equity",
                            side="buy", price=s["price"], stop=s["stop"],
                            target=s["target"], thesis="replay"),
                        pf, {}, today)
        if d.approved:
            s["qty"] = d.qty
            s["risk"] = d.qty * (s["price"] - s["stop"])
            s["notional"] = d.qty * s["price"]
            approved.append(s)
            days[s["date"]] = days.get(s["date"], 0) + 1
        else:
            why = d.reasons[-1]
            key = (why.split("binding constraint:")[-1].strip()
                   if "binding constraint" in why else why[:60])
            rejects[key] = rejects.get(key, 0) + 1

    med = lambda xs: statistics.median(xs) if xs else 0.0
    return {"symbols_scanned": scanned, "sessions": sessions,
            "equity": equity, "signals": len(signals),
            "approved": len(approved), "rejected": len(signals) - len(approved),
            "reject_reasons": rejects, "tradeable_days": len(days),
            "median_signals_per_tradeable_day": med(list(days.values())),
            "median_qty": med([a["qty"] for a in approved]),
            "median_price": med([a["price"] for a in approved]),
            "median_notional": med([a["notional"] for a in approved]),
            "median_risk": med([a["risk"] for a in approved]),
            "max_risk": max([a["risk"] for a in approved], default=0.0)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-universe", action="store_true")
    ap.add_argument("--base-rate", type=int, metavar="SESSIONS")
    ap.add_argument("--replay", type=int, metavar="SESSIONS",
                    help="replay signals through the risk engine "
                         "and report what this account could take")
    ap.add_argument("--equity", type=float, default=300.0)
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
              # .0f rounded the real $1.5M floor to "$2M" in every printed
              # report. A universe audited against the wrong threshold is the
              # same class of error as the partial bar it sits next to.
              f"min ${u['criteria']['min_dollar_volume']/1e6:.2f}M IEX dollar "
              f"volume from the {u.get('liquidity_session', '?')} session")
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

    if a.replay:
        r = replay(adapter, syms, a.replay, a.equity)
        eq = r["equity"]
        print(f"\nreplayed {r['signals']} signals from {r['symbols_scanned']} "
              f"symbols over ~{r['sessions']} sessions, at ${eq:,.0f} equity\n")
        print(f"  APPROVED by the engine : {r['approved']:4d}  "
              f"({r['approved']/r['signals']:.1%})" if r["signals"] else "  no signals")
        print(f"  REJECTED               : {r['rejected']:4d}")
        for k, v in sorted(r["reject_reasons"].items(), key=lambda kv: -kv[1]):
            print(f"      {v:4d}  {k}")
        if r["approved"]:
            print(f"\n  tradeable days: {r['tradeable_days']} of ~{r['sessions']}"
                  f"  ({r['tradeable_days']/r['sessions']:.0%}), median "
                  f"{r['median_signals_per_tradeable_day']:.0f} signals each")
            print(f"  median position: {r['median_qty']:.0f} shares @ "
                  f"${r['median_price']:.2f} = ${r['median_notional']:.2f} "
                  f"({r['median_notional']/eq:.1%} of equity)")
            print(f"  median risk    : ${r['median_risk']:.2f} "
                  f"({r['median_risk']/eq:.2%} of equity, "
                  f"{r['median_risk']/(eq*0.02):.0%} of the 2% budget); "
                  f"max ${r['max_risk']:.2f}")
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
