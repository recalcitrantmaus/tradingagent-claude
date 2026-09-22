"""Account ledger: cash, positions, realized/unrealized P&L, equity curve.

Single source of truth for 'how much money do we actually have'. The risk
engine reads from here; nothing else is allowed to assert equity.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import datetime as dt


@dataclass
class Position:
    symbol: str
    asset_class: str          # equity | etf | option | crypto
    qty: float                # contracts for options, shares/coins otherwise
    avg_price: float          # per share/coin; per *share* for options (x100)
    opened_at: dt.date
    stop: Optional[float] = None
    target: Optional[float] = None
    multiplier: int = 1       # 100 for options
    meta: Dict = field(default_factory=dict)

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_price * self.multiplier

    def market_value(self, price: float) -> float:
        return self.qty * price * self.multiplier

    def unrealized(self, price: float) -> float:
        return self.market_value(price) - self.cost_basis


@dataclass
class Fill:
    ts: dt.datetime
    symbol: str
    asset_class: str
    side: str                 # buy | sell
    qty: float
    price: float
    fees: float
    multiplier: int = 1
    reason: str = ""          # entry | stop | target | trail | time | halt

    @property
    def notional(self) -> float:
        return self.qty * self.price * self.multiplier


class Portfolio:
    def __init__(self, starting_cash: float):
        self.starting_equity = starting_cash
        self.cash = starting_cash
        self.positions: Dict[str, Position] = {}
        self.fills: List[Fill] = []
        self.realized_pnl = 0.0
        self.equity_curve: List[tuple] = []   # (date, equity)
        self.peak_equity = starting_cash
        # settlement: list of (available_date, amount) for cash-account modelling
        self._unsettled: List[tuple] = []

    # ---------- valuation ----------
    def equity(self, prices: Dict[str, float]) -> float:
        mv = 0.0
        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.avg_price)
            mv += pos.market_value(px)
        return self.cash + mv

    def settled_cash(self, today: dt.date) -> float:
        held = sum(a for d, a in self._unsettled if d > today)
        return max(0.0, self.cash - held)

    def release_settlements(self, today: dt.date) -> None:
        self._unsettled = [(d, a) for d, a in self._unsettled if d > today]

    # ---------- transactions ----------
    def buy(self, ts, symbol, asset_class, qty, price, fees, multiplier=1,
            stop=None, target=None, meta=None) -> Fill:
        cost = qty * price * multiplier + fees
        if cost > self.cash + 1e-9:
            raise ValueError(f"insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
        self.cash -= cost
        pos = self.positions.get(symbol)
        if pos is None:
            self.positions[symbol] = Position(
                symbol=symbol, asset_class=asset_class, qty=qty, avg_price=price,
                opened_at=ts.date() if hasattr(ts, "date") else ts,
                stop=stop, target=target, multiplier=multiplier, meta=meta or {})
        else:
            total = pos.qty + qty
            pos.avg_price = (pos.avg_price * pos.qty + price * qty) / total
            pos.qty = total
            if stop is not None:
                pos.stop = stop
        f = Fill(ts, symbol, asset_class, "buy", qty, price, fees, multiplier, "entry")
        self.fills.append(f)
        return f

    def sell(self, ts, symbol, qty, price, fees, reason="exit",
             settle_days: int = 0) -> Fill:
        pos = self.positions[symbol]
        qty = min(qty, pos.qty)
        proceeds = qty * price * pos.multiplier - fees
        self.realized_pnl += proceeds - qty * pos.avg_price * pos.multiplier
        self.cash += proceeds
        if settle_days > 0:
            d = (ts.date() if hasattr(ts, "date") else ts)
            self._unsettled.append((d + dt.timedelta(days=settle_days), proceeds))
        pos.qty -= qty
        if pos.qty <= 1e-9:
            del self.positions[symbol]
        f = Fill(ts, symbol, pos.asset_class, "sell", qty, price, fees,
                 pos.multiplier, reason)
        self.fills.append(f)
        return f

    # ---------- bookkeeping ----------
    def mark(self, date, prices: Dict[str, float]) -> float:
        eq = self.equity(prices)
        self.equity_curve.append((date, eq))
        self.peak_equity = max(self.peak_equity, eq)
        return eq

    def open_risk(self, prices: Dict[str, float]) -> float:
        """Dollars lost if every open stop filled, measured FROM HERE.

        T-1. Per-trade risk was capped at 2% and concurrency at 4, and nothing
        capped the sum, so the book could carry 8% at once — twice the daily
        halt and exactly the weekly one. The breakers cannot cover that gap:
        `daily_loss_halt_pct` stops NEW trades once -4% is realised, it cannot
        unwind stops already resting.

        Measured from the CURRENT price, not from entry, so a trailed stop
        genuinely frees up budget: a position at +2R with its stop at
        breakeven is no longer consuming risk, and the book should be allowed
        to use that room.

        A position with no stop is counted at FULL NOTIONAL. Nothing should
        ever create one — every entry supplies a stop — but if one exists its
        loss is unbounded, and a risk total that quietly ignores it is exactly
        the kind of comforting number this system keeps finding.
        """
        total = 0.0
        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.avg_price)
            if pos.stop is None:
                total += pos.qty * px * pos.multiplier
            else:
                total += pos.qty * max(0.0, px - pos.stop) * pos.multiplier
        return total

    def exposure_by_class(self, prices: Dict[str, float]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.avg_price)
            out[pos.asset_class] = out.get(pos.asset_class, 0.0) + pos.market_value(px)
        return out

    def drawdown(self, prices: Dict[str, float]) -> float:
        eq = self.equity(prices)
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - eq) / self.peak_equity
