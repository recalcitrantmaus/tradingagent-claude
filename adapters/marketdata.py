"""Keyless market data: Yahoo chart API for equities, CoinGecko for crypto.

Alpaca is the primary source once keys are configured. This exists because it
needs no credentials, which makes it useful in three situations: before the
broker keys are set, as an independent cross-check on Alpaca's bars, and as a
fallback when one source is down.

Neither is a contractual API. Yahoo's chart endpoint is undocumented and can
change without notice; CoinGecko's free tier is rate-limited. Both are
cross-checks, never the only source a trade depends on — if the two disagree
by more than a tolerance, `cross_check` says so and the agent should stand
down rather than pick a winner.
"""

from typing import Dict, List, Optional
import datetime as dt
import json
import urllib.error
import urllib.request

from engine.market import Bar
from .base import AdapterError

# One User-Agent for the whole agent. A second, different one here is how
# a source ends up refusing one code path and serving another.
from tools.netcheck import user_agent as _user_agent
UA = _user_agent()
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
COINGECKO = "https://api.coingecko.com/api/v3"


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read().decode()
    except urllib.error.HTTPError as e:
        raise AdapterError(f"{url} -> HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AdapterError(
            f"{url} unreachable: {e.reason}. Check the environment's network "
            "policy with `python3 -m tools.netcheck`.") from e


def daily_bars(symbol: str, rng: str = "2y") -> List[Bar]:
    """Daily OHLCV. rng: 1mo, 3mo, 6mo, 1y, 2y, 5y, max."""
    d = json.loads(_get(f"{YAHOO}/{symbol}?range={rng}&interval=1d"))
    result = (d.get("chart") or {}).get("result")
    if not result:
        err = (d.get("chart") or {}).get("error")
        raise AdapterError(f"no data for {symbol}: {err}")
    r = result[0]
    q = r["indicators"]["quote"][0]
    out: List[Bar] = []
    for i, ts in enumerate(r["timestamp"]):
        if q["close"][i] is None:
            continue
        out.append(Bar(
            dt.datetime.fromtimestamp(ts, dt.timezone.utc).date(),
            q["open"][i], q["high"][i], q["low"][i], q["close"][i],
            q["volume"][i] or 0.0))
    if not out:
        raise AdapterError(f"{symbol}: empty series")
    return out


def quote(symbol: str) -> Dict:
    d = json.loads(_get(f"{YAHOO}/{symbol}?range=1d&interval=1m"))
    meta = d["chart"]["result"][0]["meta"]
    return {"symbol": symbol,
            "price": meta.get("regularMarketPrice"),
            "previous_close": meta.get("chartPreviousClose"),
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName")}


def crypto_prices(ids: Optional[List[str]] = None) -> Dict:
    ids = ids or ["bitcoin", "ethereum"]
    d = json.loads(_get(
        f"{COINGECKO}/simple/price?ids={','.join(ids)}"
        "&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"))
    return {k: {"usd": v["usd"],
                "change_24h_pct": v.get("usd_24h_change"),
                "volume_24h": v.get("usd_24h_vol")} for k, v in d.items()}


def cross_check(symbol: str, alpaca_close: float,
                tolerance_bps: float = 50.0) -> Dict:
    """Compare a broker price against an independent one.

    A silently wrong price is the worst input this system can take: every stop
    and every size is computed from it. Disagreement is a reason to stand down
    for the session, not to average the two.
    """
    bars = daily_bars(symbol, rng="5d")
    ref = bars[-1].close
    diff_bps = abs(alpaca_close - ref) / ref * 10_000
    return {"symbol": symbol, "broker": alpaca_close, "reference": ref,
            "diff_bps": round(diff_bps, 1),
            "agree": diff_bps <= tolerance_bps,
            "note": ("prices agree" if diff_bps <= tolerance_bps else
                     f"DISAGREE by {diff_bps:.0f}bps — do not trade {symbol} "
                     "until the discrepancy is explained")}
