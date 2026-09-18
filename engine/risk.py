"""The risk officer. Every order passes through here or it does not happen.

Design rule: this module says NO by default. A proposed trade must supply a
stop; must fit every cap; and must arrive while the account is in a trading
state. The LLM-driven skills produce *proposals*; this produces *decisions*.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import datetime as dt

from .config import RiskConfig, DEFAULT
from .portfolio import Portfolio


class State(str, Enum):
    NORMAL = "NORMAL"
    DAY_HALT = "DAY_HALT"       # no new risk today; manage existing
    WEEK_HALT = "WEEK_HALT"     # no new risk this week
    LOCKED = "LOCKED"           # flattened; requires human re-authorization


@dataclass
class OrderProposal:
    symbol: str
    asset_class: str            # equity | etf | option | crypto
    side: str                   # buy | sell
    price: float                # per share/coin (per share for options)
    stop: Optional[float] = None
    target: Optional[float] = None
    multiplier: int = 1
    dte: Optional[int] = None           # options only
    defined_risk: bool = True           # options only
    minutes_since_open: Optional[int] = None
    thesis: str = ""
    qty: Optional[float] = None         # if None, risk engine sizes it
    meta: dict = field(default_factory=dict)


@dataclass
class Decision:
    approved: bool
    qty: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def reject(self, why: str) -> "Decision":
        self.approved = False
        self.qty = 0.0
        self.reasons.append(why)
        return self


class RiskOfficer:
    def __init__(self, cfg: RiskConfig = DEFAULT):
        self.cfg = cfg
        self.state = State.NORMAL
        self.day_start_equity: Optional[float] = None
        self.week_start_equity: Optional[float] = None
        self.consecutive_losses = 0
        self.day_trades: List[dt.date] = []
        self.journal: List[str] = []
        # Measured track record, supplied by tools.review from the real fill
        # log. Defaults are deliberately disqualifying: an agent with no
        # record does not get the instrument that punishes not having one.
        self.closed_trades: int = 0
        self.expectancy_R: float = 0.0

    # ------------------------------------------------------------------
    # session lifecycle
    # ------------------------------------------------------------------
    def start_day(self, date: dt.date, equity: float) -> None:
        self.day_start_equity = equity
        if self.week_start_equity is None or date.weekday() == 0:
            self.week_start_equity = equity
        if self.state == State.DAY_HALT:
            self.state = State.NORMAL
        if self.state == State.WEEK_HALT and date.weekday() == 0:
            self.state = State.NORMAL
        self.consecutive_losses = 0
        self.day_trades = [d for d in self.day_trades
                           if (date - d).days < 5]

    def update(self, date: dt.date, portfolio: Portfolio,
               prices: Dict[str, float]) -> State:
        """Re-evaluate circuit breakers. Call after every fill and every mark."""
        eq = portfolio.equity(prices)
        c = self.cfg

        if portfolio.drawdown(prices) >= c.max_drawdown_lock_pct:
            self._escalate(State.LOCKED,
                           f"drawdown {portfolio.drawdown(prices):.1%} >= "
                           f"{c.max_drawdown_lock_pct:.0%} from peak "
                           f"{portfolio.peak_equity:.2f}")
            return self.state

        if self.week_start_equity:
            wk = (eq - self.week_start_equity) / self.week_start_equity
            if wk <= -c.weekly_loss_halt_pct and self.state in (State.NORMAL, State.DAY_HALT):
                self._escalate(State.WEEK_HALT, f"week P&L {wk:.1%} <= -{c.weekly_loss_halt_pct:.0%}")
                return self.state

        if self.day_start_equity:
            dy = (eq - self.day_start_equity) / self.day_start_equity
            if dy <= -c.daily_loss_halt_pct and self.state == State.NORMAL:
                self._escalate(State.DAY_HALT, f"day P&L {dy:.1%} <= -{c.daily_loss_halt_pct:.0%}")
                return self.state

        if self.consecutive_losses >= c.consecutive_loss_halt and self.state == State.NORMAL:
            self._escalate(State.DAY_HALT,
                           f"{self.consecutive_losses} consecutive losing trades")
        return self.state

    def record_trade_result(self, pnl: float) -> None:
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0

    def record_day_trade(self, date: dt.date) -> None:
        self.day_trades.append(date)

    def set_track_record(self, closed_trades: int, expectancy_R: float) -> None:
        """Feed measured performance in. Call from tools.review before trading."""
        self.closed_trades = closed_trades
        self.expectancy_R = expectancy_R

    def _escalate(self, new: State, why: str) -> None:
        order = [State.NORMAL, State.DAY_HALT, State.WEEK_HALT, State.LOCKED]
        if order.index(new) > order.index(self.state):
            self.journal.append(f"{self.state} -> {new}: {why}")
            self.state = new

    def unlock(self, authorization: str) -> None:
        """Only a human may clear LOCKED. Recorded verbatim in the journal."""
        if not authorization.strip():
            raise ValueError("unlock requires a human authorization note")
        self.journal.append(f"{self.state} -> NORMAL by human: {authorization}")
        self.state = State.NORMAL

    # ------------------------------------------------------------------
    # the gate
    # ------------------------------------------------------------------
    def evaluate(self, p: OrderProposal, portfolio: Portfolio,
                 prices: Dict[str, float], date: dt.date) -> Decision:
        c, d = self.cfg, Decision(approved=True)

        if p.side != "buy":
            d.reasons.append("exits are always permitted")
            return d

        if self.state != State.NORMAL:
            return d.reject(f"account state is {self.state.value}; no new risk")

        eq = portfolio.equity(prices)
        if eq <= 0:
            return d.reject("no equity")

        # --- universal requirements ---
        if p.stop is None:
            return d.reject("no stop supplied; every entry must define its exit")
        if p.stop >= p.price:
            return d.reject("stop is not below entry")
        if len(portfolio.positions) >= c.max_concurrent_positions \
                and p.symbol not in portfolio.positions:
            return d.reject(f"already at max {c.max_concurrent_positions} positions")


        # --- asset-class specific gates ---
        if p.asset_class == "option":
            if eq < c.option_min_equity:
                return d.reject(
                    f"equity {eq:.2f} < {c.option_min_equity:.0f} option floor: "
                    "a single contract's max loss would exceed the risk budget")
            if c.option_requires_proven_edge:
                if self.closed_trades < c.option_min_closed_trades:
                    return d.reject(
                        f"option sleeve locked: {self.closed_trades} closed trades "
                        f"< {c.option_min_closed_trades} needed to measure an edge")
                if self.expectancy_R < c.option_min_expectancy_R:
                    return d.reject(
                        f"option sleeve locked: measured expectancy "
                        f"{self.expectancy_R:+.3f}R < required "
                        f"{c.option_min_expectancy_R:+.2f}R")
            if p.dte is None or p.dte < c.option_min_dte:
                return d.reject(f"option DTE {p.dte} < minimum {c.option_min_dte}")
            if p.dte > c.option_max_dte:
                return d.reject(f"option DTE {p.dte} > maximum {c.option_max_dte}")
            if c.option_defined_risk_only and not p.defined_risk:
                return d.reject("undefined-risk option structure")
            if p.minutes_since_open is not None \
                    and p.minutes_since_open < c.option_observe_open_minutes:
                return d.reject(
                    f"only {p.minutes_since_open} min since the open; "
                    f"observe {c.option_observe_open_minutes}")
            if c.assume_pdt_regime and len(self.day_trades) >= c.max_day_trades_per_5d:
                d.reasons.append("at day-trade budget: this must be held overnight")

        # --- reward to risk, in code rather than in a skill file ---
        if c.require_target and p.target is None:
            return d.reject("no target supplied; expected R cannot be graded")
        if p.target is not None:
            if p.target <= p.price:
                return d.reject("target is not above entry")
            expected_r = (p.target - p.price) / (p.price - p.stop)
            # Tolerance, not laxity. The config's own option exit pair — a -40%
            # stop against a +60% take-profit — is 0.60/0.40, which in binary
            # floating point is 1.4999999999999998 and fails a naive `< 1.5`.
            # A rule that rejects its own documented defaults by 2e-16 would
            # surface as an inexplicable rejection with a correct-looking
            # reason string, which is the worst kind to debug.
            if expected_r < c.min_expected_r - 1e-9:
                return d.reject(
                    f"expected R {expected_r:.2f} < required "
                    f"{c.min_expected_r:.2f}; the target is too close to the "
                    f"entry for the stop being taken")
            d.reasons.append(f"expected R {expected_r:.2f}")

        # --- sizing ---
        risk_per_unit = (p.price - p.stop) * p.multiplier
        if risk_per_unit <= 0:
            return d.reject("non-positive risk per unit")

        risk_budget = eq * c.max_risk_per_trade_pct
        qty_by_risk = risk_budget / risk_per_unit

        pos_cap_pct = {
            "option": c.max_position_pct_option,
            "crypto": c.max_position_pct_crypto,
        }.get(p.asset_class, c.max_position_pct_equity)
        qty_by_position = (eq * pos_cap_pct) / (p.price * p.multiplier)

        # aggregate class cap
        exposure = portfolio.exposure_by_class(prices)
        class_cap = c.class_caps.get(p.asset_class, 0.0) * eq
        room = max(0.0, class_cap - exposure.get(p.asset_class, 0.0))
        qty_by_class = room / (p.price * p.multiplier)

        deployable = portfolio.settled_cash(date) - eq * c.min_cash_reserve_pct
        qty_by_cash = max(0.0, deployable) / (p.price * p.multiplier)

        qty = min(qty_by_risk, qty_by_position, qty_by_class, qty_by_cash)
        if p.qty is not None:
            qty = min(qty, p.qty)

        if p.asset_class in ("equity", "etf", "option"):
            qty = float(int(qty))         # whole shares / whole contracts
        if p.asset_class == "option" and eq < 1000:
            qty = min(qty, c.max_option_contracts_under_1k)

        if qty <= 0:
            binding = min(
                (qty_by_risk, "2% risk budget"),
                (qty_by_position, "single-position cap"),
                (qty_by_class, f"{p.asset_class} class cap"),
                (qty_by_cash, "settled cash after reserve"),
                key=lambda t: t[0])[1]
            return d.reject(f"size rounds to zero; binding constraint: {binding}")

        d.qty = qty
        d.reasons.append(
            f"sized {qty:g} @ {p.price:.2f}, risking "
            f"{qty * risk_per_unit:.2f} ({qty * risk_per_unit / eq:.2%} of equity)")
        return d

    # ------------------------------------------------------------------
    def mandatory_stop(self, entry: float, atr: Optional[float],
                       asset_class: str) -> float:
        """The widest stop the constitution allows for a given entry."""
        c = self.cfg
        if asset_class == "option":
            return entry * (1 - c.option_stop_premium_pct)
        floor = entry * (1 - c.equity_stop_max_pct)
        if atr:
            return max(floor, entry - c.equity_stop_atr_mult * atr)
        return floor
