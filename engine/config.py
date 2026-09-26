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
    # Aggregate open risk across the whole book, as a fraction of equity.
    # T-1 (2026-09-22): 4 positions x 2% could put 8% at risk simultaneously,
    # which is 2x daily_loss_halt_pct and exactly weekly_loss_halt_pct. Set
    # equal to the daily halt so the invariant is simple and checkable: if
    # every stop filled at once, the loss is exactly the day's limit and the
    # breaker is a real ceiling rather than a marker read after the fact.
    #
    # This is the only diversification control that works here. Measured
    # 2026-09-22 on the day's own signals, 60-day daily-return correlation
    # ran 0.45 to 0.83 across every pair including a space name and a broad
    # ETF — a long-only breakout book has no uncorrelated pair to spread
    # into, so limiting the TOTAL is the lever, not choosing names.
    max_portfolio_risk_pct: float = 0.04
    # Each ADDITIONAL concurrent position gets this fraction of the previous
    # one's risk budget: 1st 2.00%, 2nd 2.00*d, 3rd 2.00*d^2, ...
    #
    # This is the size-based form of "conservative on most, let one run". The
    # target is the wrong lever for that: a target controls upside, while size
    # and the stop control loss. Cutting targets on the also-rans would give
    # up their winners while keeping their full downside — precisely backwards.
    # Cutting SIZE gives the strongest conviction full weight and makes every
    # subsequent correlated add cheaper to be wrong about.
    #
    # It needs no correlation input, and that is a measurement rather than a
    # convenience: on 2026-09-22 the minimum pairwise 60-day correlation
    # across the day's own signals was 0.45, including a space company against
    # a semiconductor. There is no uncorrelated pair to detect, so treating
    # every addition as correlated is the conservative and honest default, and
    # it keeps the engine deterministic with no live data inside it.
    #
    # 0.5 chosen by sweep, 3000 seeds, two strategies. Unlike the portfolio
    # cap above — which bought safety by giving up median — this is a genuine
    # Pareto improvement: on momentum_breakout it moved median +1.65, p05
    # +10.00, mean max drawdown 8.9%->6.4%, WORST drawdown 20.9%->17.8% and
    # locked accounts 15/3000 -> 0 (z = -3.88). The mechanism is visible in
    # that worst-drawdown figure: the lock threshold is -20%, and the taper
    # pulls the worst case under it. 1.0 disables it. docs/04-lessons.md.
    correlated_risk_decay: float = 0.5

    # --- asset-class caps (fraction of equity, aggregate) ---
    class_caps: Dict[str, float] = field(default_factory=lambda: {
        "equity": 0.90,
        "etf": 0.90,
        "option": 0.30,   # premium at risk across all open options
        "crypto": 0.20,
    })

    # --- reward to risk ---
    # "Expected R >= 1.5" was written in CLAUDE.md, the runbook and the
    # trade-plan skill from the beginning, and existed in none of them as code:
    # RiskOfficer.evaluate never read `target`, so the gate was unreachable.
    # The simulator did not catch it because every simulated strategy sets
    # target = entry + 3*ATR against a 1.5*ATR stop, which is 2.0R by
    # construction and could not have failed a 1.5 gate even if one had run.
    min_expected_r: float = 1.5
    require_target: bool = True      # no target, no grade, no trade

    # --- mandatory exits ---
    equity_stop_atr_mult: float = 1.5        # stop = entry - 1.5 * ATR(14)
    equity_stop_max_pct: float = 0.08        # ...but never wider than 8%
    option_stop_premium_pct: float = 0.40    # cut a long option at -40% premium
    option_take_profit_pct: float = 0.60     # scale out at +60% premium
    scale_out_fraction: float = 0.50         # take half off at the first target
    trail_after_r: float = 1.0               # trail the rest once +1R is banked
    # Exit an equity position after this many business days held. 0 = off,
    # which is the rule today. Added 2026-09-26 for D-24: the no-target arm
    # exits only on its stop or on a time stop, and the simulator had no time
    # stop, so the arm could not be tested inside the engine.
    max_holding_days: int = 0

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
    # W-3 (2026-09-26, recalcitrantmaus): "The pattern day trader rule should not apply
    # to the cash account at all, nor will it be flagged in Robinhood." Both
    # accounts are cash accounts. The broker payload shows multiplier 1, no
    # shorting, and no daytrade_count field. A cash account's intraday
    # constraint is settlement, and `cash_account_settlement_days` plus
    # `Portfolio.settled_cash` already gate that. Day trades are still COUNTED
    # (W-1) and shown. Setting this True restores the 3-in-5 budget if a
    # margin account is ever used.
    assume_pdt_regime: bool = False
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
