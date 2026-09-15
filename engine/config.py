"""Risk and account configuration.

These numbers are the agent's hard constitution. The skills in .claude/skills
may reason freely about *what* to trade; they may never widen these bounds.
Only a human editing this file (and the tests that pin it) can do that.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict
import json


@dataclass(frozen=True)
class RiskConfig:
    # --- account ---
    starting_equity: float = 300.0
    min_cash_reserve_pct: float = 0.10       # never deploy the last 10%

    # --- per-trade sizing ---
    max_risk_per_trade_pct: float = 0.02     # max 2% of equity lost if stop hits
    max_position_pct_equity: float = 0.25    # any single equity/ETF position
    max_position_pct_option: float = 0.15    # any single option position (premium)
    max_position_pct_crypto: float = 0.15
    max_concurrent_positions: int = 4

    # --- asset-class caps (fraction of equity, aggregate) ---
    class_caps: Dict[str, float] = field(default_factory=lambda: {
        "equity": 0.90,
        "etf": 0.90,
        "option": 0.30,   # premium at risk across all open options
        "crypto": 0.20,
    })

    # --- mandatory exits ---
    equity_stop_atr_mult: float = 1.5        # stop = entry - 1.5 * ATR(14)
    equity_stop_max_pct: float = 0.08        # ...but never wider than 8%
    option_stop_premium_pct: float = 0.40    # cut a long option at -40% premium
    option_take_profit_pct: float = 0.60     # scale out at +60% premium
    scale_out_fraction: float = 0.50         # take half off at the first target
    trail_after_r: float = 1.0               # trail the rest once +1R is banked

    # --- circuit breakers (state machine in risk.py) ---
    daily_loss_halt_pct: float = 0.04        # -4% on the day  -> stop for the day
    weekly_loss_halt_pct: float = 0.08       # -8% on the week -> stop for the week
    max_drawdown_lock_pct: float = 0.20      # -20% from peak  -> flatten + lock
    consecutive_loss_halt: int = 4           # 4 losers in a row -> stop for the day

    # --- options discipline ---
    option_min_dte: int = 7                  # no 0DTE / no lottery tickets
    option_max_dte: int = 45
    option_defined_risk_only: bool = True    # long premium or debit spreads only
    option_observe_open_minutes: int = 15    # no contracts in the first 15 min
    max_option_contracts_under_1k: int = 1
    # Derived in simulation (see docs/05-sim-report.md): for a 2% risk budget
    # to fund even one contract at a 40% premium stop, equity must exceed
    # 2000 x premium. The cheapest liquid contracts run $0.50-1.00, so options
    # are structurally unaffordable below roughly $1,500 of equity. Below this
    # line the agent compounds with shares/ETFs only.
    option_min_equity: float = 1500.0
    # Capital was never the real problem. A sweep across $300-$10,000 found
    # long-premium buying negative at EVERY level (-14% to -15% median at
    # $2.5k+) and under every stop setting tested, because the strategy pays
    # an implied-vol premium on entry and spread on both sides. So the equity
    # floor is necessary but nowhere near sufficient: the option sleeve also
    # stays locked until the account has demonstrated a positive edge with
    # instruments that do not bleed. See docs/05-sim-report.md Result 7.
    option_requires_proven_edge: bool = True
    option_min_closed_trades: int = 30       # before expectancy means anything
    option_min_expectancy_R: float = 0.10    # measured, in the real account

    # --- day-trade governance ---
    # FINRA replaced the PDT $25k regime with intraday margin standards
    # effective 2026-06-04, with broker phase-in allowed until 2027-10-20.
    # Until we confirm Robinhood's implementation we model the strict case.
    assume_pdt_regime: bool = True
    max_day_trades_per_5d: int = 3
    cash_account_settlement_days: int = 1    # T+1

    # --- costs (paper broker must not flatter us) ---
    equity_slippage_bps: float = 5.0
    option_slippage_per_contract: float = 0.03   # $0.03 of a $X.XX quote, per share
    option_contract_fee: float = 0.03            # exchange/regulatory, per contract
    crypto_spread_bps: float = 35.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


DEFAULT = RiskConfig()
