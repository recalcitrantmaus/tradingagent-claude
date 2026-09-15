"""Daily-bar simulation harness.

Rules that keep the results honest:
  * No look-ahead: a strategy only sees bars up to and including today's close,
    and any entry it proposes is filled at the NEXT open.
  * Pessimistic intrabar ordering: if a bar touches both the stop and the
    target, the stop is assumed to have been hit first.
  * Options are repriced daily with Black-Scholes on the live underlying,
    with theta and the DTE floor applied. No magic exits at the high.
  * Every fill pays spread, slippage and fees.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import datetime as dt
import statistics

from .config import RiskConfig, DEFAULT
from .market import SyntheticMarket, black_scholes, realized_vol
from .portfolio import Portfolio
from .risk import RiskOfficer, State, OrderProposal
from .broker import PaperBroker
from .strategies import Strategy


@dataclass
class SimResult:
    name: str
    seed: int
    starting_equity: float
    final_equity: float
    equity_curve: List[float] = field(default_factory=list)
    weekly_returns: List[float] = field(default_factory=list)
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_win: float = 0.0
    gross_loss: float = 0.0
    fees_paid: float = 0.0
    max_drawdown: float = 0.0
    end_state: str = "NORMAL"
    halts: List[str] = field(default_factory=list)
    rejections: Dict[str, int] = field(default_factory=dict)

    @property
    def total_return(self) -> float:
        return self.final_equity / self.starting_equity - 1

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        return self.gross_win / abs(self.gross_loss) if self.gross_loss else float("inf")

    @property
    def mean_weekly(self) -> float:
        return statistics.mean(self.weekly_returns) if self.weekly_returns else 0.0

    @property
    def median_weekly(self) -> float:
        return statistics.median(self.weekly_returns) if self.weekly_returns else 0.0

    @property
    def weeks_hitting_5pct(self) -> float:
        if not self.weekly_returns:
            return 0.0
        return sum(1 for r in self.weekly_returns if r >= 0.05) / len(self.weekly_returns)

    @property
    def ruined(self) -> bool:
        return self.final_equity <= self.starting_equity * 0.5


def _option_price(pos, mkt: SyntheticMarket, i: int, cfg) -> float:
    m = pos.meta
    u = mkt.history[m["underlying"]][i].close
    dte = max(0, m["expiry_index"] - i)
    return max(0.01, black_scholes(u, m["strike"], dte, m["iv"], m["kind"]))


def run(strategy: Strategy, mkt: SyntheticMarket, cfg: RiskConfig = DEFAULT,
        seed: int = 0, warmup: int = 55, settle: bool = True) -> SimResult:
    pf = Portfolio(cfg.starting_equity)
    ro = RiskOfficer(cfg)
    bk = PaperBroker(pf, cfg)
    res = SimResult(strategy.name, seed, cfg.starting_equity, cfg.starting_equity)

    pending: List[OrderProposal] = []
    week_anchor: Optional[float] = None
    settle_days = cfg.cash_account_settlement_days if settle else 0

    for i, date in enumerate(mkt.dates):
        ts = dt.datetime.combine(date, dt.time(9, 30))
        closes = mkt.closes_on(i)

        def price_of(sym) -> float:
            pos = pf.positions.get(sym)
            if pos and pos.asset_class == "option":
                return _option_price(pos, mkt, i, cfg)
            return closes.get(sym, 0.0)

        prices = {s: price_of(s) for s in list(pf.positions) + list(closes)}
        pf.release_settlements(date)
        eq_open = pf.equity(prices)
        ro.start_day(date, eq_open)
        if week_anchor is None:
            week_anchor = eq_open

        # ---- 1. fill yesterday's approved entries at today's open ----
        for prop in pending:
            if prop.asset_class == "option":
                prop.price = _option_price_from_meta(prop, mkt, i)
                prop.stop = prop.price * (1 - cfg.option_stop_premium_pct)
                prop.target = prop.price * (1 + cfg.option_take_profit_pct)
            else:
                prop.price = mkt.history[prop.symbol][i].open
            d = ro.evaluate(prop, pf, prices, date)
            if not d.approved:
                for r in d.reasons:
                    key = r.split(";")[0][:60]
                    res.rejections[key] = res.rejections.get(key, 0) + 1
                continue
            fill = bk.execute(ts, prop, d)
            if fill:
                res.fees_paid += fill.fees
        pending = []

        # ---- 2. manage open positions against today's range ----
        for sym in list(pf.positions):
            pos = pf.positions[sym]
            if pos.asset_class == "option":
                px = _option_price(pos, mkt, i, cfg)
                low = high = px
                expiring = (pos.meta["expiry_index"] - i) <= cfg.option_min_dte
            else:
                bar = mkt.history[sym][i]
                low, high, px = bar.low, bar.high, bar.close
                expiring = False

            reason = None
            exit_px = px
            if pos.stop is not None and low <= pos.stop:
                reason, exit_px = "stop", pos.stop      # pessimistic: stop first
            elif pos.target is not None and high >= pos.target:
                reason, exit_px = "target", pos.target
            elif expiring:
                reason, exit_px = "time", px
            elif ro.state in (State.WEEK_HALT, State.LOCKED):
                reason, exit_px = "halt", px

            if reason == "target" and cfg.scale_out_fraction < 1.0 and pos.qty > 1:
                qty = max(1.0, round(pos.qty * cfg.scale_out_fraction))
                _, pnl = bk.close(ts, sym, exit_px, "scale_out", qty=qty,
                                  settle_days=settle_days)
                pos.stop = max(pos.stop or 0, pos.avg_price)   # rest goes risk-free
                _tally(res, ro, pnl)
            elif reason:
                _, pnl = bk.close(ts, sym, exit_px, reason, settle_days=settle_days)
                _tally(res, ro, pnl)

            prices = {s: price_of(s) for s in list(pf.positions) + list(closes)}
            ro.update(date, pf, prices)

        # ---- 3. propose tomorrow's entries from today's close ----
        if i >= warmup and ro.state == State.NORMAL:
            pending = strategy.propose(mkt, i, pf, cfg)[:cfg.max_concurrent_positions]

        # ---- 4. mark ----
        prices = {s: price_of(s) for s in list(pf.positions) + list(closes)}
        eq = pf.mark(date, prices)
        res.equity_curve.append(eq)
        res.max_drawdown = max(res.max_drawdown, pf.drawdown(prices))
        ro.update(date, pf, prices)

        if date.weekday() == 4 and week_anchor:
            res.weekly_returns.append(eq / week_anchor - 1)
            week_anchor = eq

    res.final_equity = res.equity_curve[-1] if res.equity_curve else cfg.starting_equity
    res.end_state = ro.state.value
    res.halts = list(ro.journal)
    return res


def _option_price_from_meta(prop: OrderProposal, mkt: SyntheticMarket, i: int) -> float:
    m = prop.meta
    u = mkt.history[m["underlying"]][i].open
    dte = max(0, m["expiry_index"] - i)
    return max(0.01, black_scholes(u, m["strike"], dte, m["iv"], m["kind"]))


def _tally(res: SimResult, ro: RiskOfficer, pnl: float) -> None:
    res.trades += 1
    if pnl >= 0:
        res.wins += 1
        res.gross_win += pnl
    else:
        res.losses += 1
        res.gross_loss += pnl
    ro.record_trade_result(pnl)
