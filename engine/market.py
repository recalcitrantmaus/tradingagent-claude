"""Market data: offline CSV loader + a synthetic generator for simulation.

This session's network policy blocks every market-data host (see
docs/03-environment-constraints.md), so simulation runs on a generator that
is deliberately *unkind*: regime switching, fat tails, gaps and jumps. A
strategy that only survives on clean geometric Brownian motion is not a
strategy.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
import csv
import datetime as dt
import math
import random


@dataclass
class Bar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


# ----------------------------------------------------------------------
# indicators
# ----------------------------------------------------------------------
def atr(bars: Sequence[Bar], n: int = 14) -> Optional[float]:
    if len(bars) < n + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-n - 1:-1], bars[-n:]):
        trs.append(max(cur.high - cur.low,
                       abs(cur.high - prev.close),
                       abs(cur.low - prev.close)))
    return sum(trs) / len(trs)


def sma(bars: Sequence[Bar], n: int) -> Optional[float]:
    if len(bars) < n:
        return None
    return sum(b.close for b in bars[-n:]) / n


def rsi(bars: Sequence[Bar], n: int = 14) -> Optional[float]:
    if len(bars) < n + 1:
        return None
    gains = losses = 0.0
    for prev, cur in zip(bars[-n - 1:-1], bars[-n:]):
        ch = cur.close - prev.close
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def realized_vol(bars: Sequence[Bar], n: int = 20) -> Optional[float]:
    """Annualized close-to-close volatility."""
    if len(bars) < n + 1:
        return None
    rets = [math.log(b.close / a.close)
            for a, b in zip(bars[-n - 1:-1], bars[-n:]) if a.close > 0]
    if len(rets) < 2:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * 252)


# ----------------------------------------------------------------------
# option pricing (for simulating option P&L honestly)
# ----------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes(spot: float, strike: float, dte_days: int, vol: float,
                  kind: str = "call", rate: float = 0.04) -> float:
    """Per-share premium. dte in calendar days."""
    t = max(dte_days, 0) / 365.0
    if t <= 0 or vol <= 0:
        intrinsic = spot - strike if kind == "call" else strike - spot
        return max(intrinsic, 0.0)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol ** 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if kind == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * t) * _norm_cdf(d2)
    return strike * math.exp(-rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


# ----------------------------------------------------------------------
# synthetic market
# ----------------------------------------------------------------------
REGIMES = {
    #            annual drift, annual vol, persistence
    "bull":     (0.22, 0.14, 0.97),
    "chop":     (0.00, 0.18, 0.95),
    "bear":     (-0.30, 0.34, 0.94),
    "crisis":   (-0.80, 0.65, 0.85),
}


class SyntheticMarket:
    """Correlated daily bars with regime switching and jump risk.

    Every symbol is beta-loaded onto a common market factor, so the
    portfolio cannot diversify away a crisis — which is the point.
    """

    def __init__(self, symbols: Dict[str, dict], days: int, seed: int = 0,
                 start: dt.date = dt.date(2025, 1, 2)):
        """symbols: {sym: {"beta": float, "idio_vol": float, "px": float,
                           "asset_class": str}}"""
        self.rng = random.Random(seed)
        self.symbols = symbols
        self.days = days
        self.start = start
        self.history: Dict[str, List[Bar]] = {s: [] for s in symbols}
        self.dates: List[dt.date] = []
        self.regime_log: List[str] = []
        self._generate()

    def _generate(self) -> None:
        px = {s: cfg["px"] for s, cfg in self.symbols.items()}
        regime = "chop"
        d = self.start
        for _ in range(self.days):
            while d.weekday() >= 5:
                d += dt.timedelta(days=1)

            mu, vol, persist = REGIMES[regime]
            if self.rng.random() > persist:
                regime = self.rng.choices(
                    list(REGIMES), weights=[0.42, 0.34, 0.19, 0.05])[0]
            self.regime_log.append(regime)

            # market factor with a fat tail
            z = self.rng.gauss(0, 1)
            if self.rng.random() < 0.02:                     # jump day
                z += self.rng.choice([-1, 1]) * self.rng.uniform(2.5, 5.0)
            factor = mu / 252 + vol / math.sqrt(252) * z

            for s, cfg in self.symbols.items():
                idio = self.rng.gauss(0, cfg["idio_vol"] / math.sqrt(252))
                ret = cfg["beta"] * factor + idio
                o = px[s] * (1 + self.rng.gauss(0, 0.002))   # overnight gap
                c = px[s] * math.exp(ret)
                intraday = abs(self.rng.gauss(0, 0.008)) * c
                h = max(o, c) + intraday
                l = min(o, c) - intraday
                self.history[s].append(
                    Bar(d, round(o, 4), round(h, 4), round(l, 4), round(c, 4),
                        self.rng.uniform(5e5, 5e7)))
                px[s] = c

            self.dates.append(d)
            d += dt.timedelta(days=1)

    def bars_through(self, symbol: str, i: int) -> List[Bar]:
        """History visible at the close of day index i (no look-ahead)."""
        return self.history[symbol][:i + 1]

    def closes_on(self, i: int) -> Dict[str, float]:
        return {s: self.history[s][i].close for s in self.symbols}


def load_csv(path: str) -> List[Bar]:
    """date,open,high,low,close,volume — for when real data is available."""
    out = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            out.append(Bar(dt.date.fromisoformat(row["date"]),
                           float(row["open"]), float(row["high"]),
                           float(row["low"]), float(row["close"]),
                           float(row.get("volume", 0))))
    return out
