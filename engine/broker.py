"""Paper broker. Charges realistic frictions so simulations do not flatter us.

A $300 account is destroyed by costs long before it is destroyed by bad
opinions, so costs are modelled first-class: spread, slippage, per-contract
fees, and T+1 settlement on the cash-account model.
"""

from typing import Dict, Optional
import datetime as dt

from .config import RiskConfig, DEFAULT
from .portfolio import Portfolio
from .risk import OrderProposal, Decision


class PaperBroker:
    def __init__(self, portfolio: Portfolio, cfg: RiskConfig = DEFAULT):
        self.p = portfolio
        self.cfg = cfg

    # ---- friction ----
    def fill_price(self, p_price: float, asset_class: str, side: str) -> float:
        c = self.cfg
        sign = 1 if side == "buy" else -1
        if asset_class == "crypto":
            return p_price * (1 + sign * c.crypto_spread_bps / 10_000)
        if asset_class == "option":
            return max(0.01, p_price + sign * c.option_slippage_per_contract)
        return p_price * (1 + sign * c.equity_slippage_bps / 10_000)

    def fees(self, asset_class: str, qty: float) -> float:
        if asset_class == "option":
            return qty * self.cfg.option_contract_fee
        return 0.0

    # ---- execution ----
    def execute(self, ts: dt.datetime, prop: OrderProposal, decision: Decision):
        if not decision.approved or decision.qty <= 0:
            return None
        px = self.fill_price(prop.price, prop.asset_class, prop.side)
        fee = self.fees(prop.asset_class, decision.qty)
        cost = decision.qty * px * prop.multiplier + fee
        if cost > self.p.cash:
            # shave size rather than fail: frictions moved the price against us
            affordable = int((self.p.cash - fee) / (px * prop.multiplier))
            if affordable <= 0:
                return None
            decision.qty = float(affordable)
            fee = self.fees(prop.asset_class, decision.qty)
        return self.p.buy(ts, prop.symbol, prop.asset_class, decision.qty, px, fee,
                          multiplier=prop.multiplier, stop=prop.stop,
                          target=prop.target,
                          meta={"thesis": prop.thesis, **prop.meta})

    def close(self, ts: dt.datetime, symbol: str, price: float, reason: str,
              qty: Optional[float] = None, settle_days: int = 0):
        pos = self.p.positions[symbol]
        qty = pos.qty if qty is None else min(qty, pos.qty)
        px = self.fill_price(price, pos.asset_class, "sell")
        fee = self.fees(pos.asset_class, qty)
        entry_cost = qty * pos.avg_price * pos.multiplier
        fill = self.p.sell(ts, symbol, qty, px, fee, reason=reason,
                           settle_days=settle_days)
        pnl = qty * px * pos.multiplier - fee - entry_cost
        return fill, pnl
