"""Baseline strategies used to stress the risk engine in simulation.

These are NOT the agent's trading intelligence. In production the entries
come from the skills (research + news + technicals). These exist so the
guardrails can be tested against thousands of trades, and so we have a
sober prior for what a $300 account can actually earn.
"""

from typing import List, Optional
import datetime as dt

from .market import SyntheticMarket, atr, sma, rsi, realized_vol, black_scholes
from .risk import OrderProposal


class Strategy:
    name = "base"

    def propose(self, mkt: SyntheticMarket, i: int, portfolio, cfg) -> List[OrderProposal]:
        return []


class TrendPullback(Strategy):
    """Buy strength on weakness: above the 50-day, RSI(14) oversold."""
    name = "trend_pullback"

    def propose(self, mkt, i, portfolio, cfg):
        out = []
        for sym, meta in mkt.symbols.items():
            if meta["asset_class"] not in ("equity", "etf"):
                continue
            if sym in portfolio.positions:
                continue
            bars = mkt.bars_through(sym, i)
            s50, r, a = sma(bars, 50), rsi(bars, 14), atr(bars, 14)
            if not (s50 and r and a):
                continue
            px = bars[-1].close
            if px > s50 and r < 40:
                stop = max(px - 1.5 * a, px * 0.92)
                out.append(OrderProposal(
                    symbol=sym, asset_class=meta["asset_class"], side="buy",
                    price=px, stop=stop, target=px + 3.0 * a,
                    thesis=f"above 50DMA ({px:.2f}>{s50:.2f}), RSI {r:.0f} reset"))
        return out


class MomentumBreakout(Strategy):
    """Buy 20-day highs with a volatility-scaled stop."""
    name = "momentum_breakout"

    def propose(self, mkt, i, portfolio, cfg):
        out = []
        for sym, meta in mkt.symbols.items():
            if sym in portfolio.positions:
                continue
            bars = mkt.bars_through(sym, i)
            if len(bars) < 21:
                continue
            a = atr(bars, 14)
            if not a:
                continue
            px = bars[-1].close
            prior_high = max(b.high for b in bars[-21:-1])
            if px > prior_high:
                out.append(OrderProposal(
                    symbol=sym, asset_class=meta["asset_class"], side="buy",
                    price=px, stop=max(px - 1.5 * a, px * 0.92),
                    target=px + 3.0 * a,
                    thesis=f"20-day breakout over {prior_high:.2f}"))
        return out


class OptionSwing(Strategy):
    """~30 DTE slightly-OTM calls on trend confirmation. Defined risk only."""
    name = "option_swing"
    dte = 30

    def propose(self, mkt, i, portfolio, cfg):
        out = []
        for sym, meta in mkt.symbols.items():
            if meta["asset_class"] not in ("equity", "etf"):
                continue
            key = f"{sym}_C"
            if key in portfolio.positions:
                continue
            bars = mkt.bars_through(sym, i)
            s20, s50 = sma(bars, 20), sma(bars, 50)
            vol = realized_vol(bars, 20)
            if not (s20 and s50 and vol):
                continue
            px = bars[-1].close
            if not (px > s20 > s50):
                continue
            strike = round(px * 1.02, 0)
            iv = max(0.12, vol * 1.15)          # IV carries a premium to RV
            prem = black_scholes(px, strike, self.dte, iv, "call")
            if prem <= 0.05:
                continue
            out.append(OrderProposal(
                symbol=key, asset_class="option", side="buy", price=prem,
                stop=prem * (1 - cfg.option_stop_premium_pct),
                target=prem * (1 + cfg.option_take_profit_pct),
                multiplier=100, dte=self.dte, defined_risk=True,
                minutes_since_open=cfg.option_observe_open_minutes,
                thesis=f"{sym} {px:.2f} > 20DMA > 50DMA; {strike:.0f}C {self.dte}DTE @ {prem:.2f}",
                meta={"underlying": sym, "strike": strike, "kind": "call",
                      "iv": iv, "expiry_index": i + self.dte}))
        return out


class GraduatedSwing(Strategy):
    """Trades stock first; adds the option sleeve only once the risk engine
    unlocks it. This is the shape the live agent should have — the account
    earns its way into the harder instrument instead of starting there.
    """
    name = "graduated_swing"

    def __init__(self):
        self.equity_leg = MomentumBreakout()
        self.option_leg = OptionSwing()

    def propose(self, mkt, i, portfolio, cfg):
        return self.equity_leg.propose(mkt, i, portfolio, cfg) \
            + self.option_leg.propose(mkt, i, portfolio, cfg)


class TargetChaser(Strategy):
    """Deliberately reckless control: what 5%/week actually requires.

    Sized to hit the weekly target in a handful of trades. Kept in the repo
    as a falsifiable control for the feasibility argument, never for live use.
    """
    name = "target_chaser_CONTROL"

    def propose(self, mkt, i, portfolio, cfg):
        out = []
        for sym, meta in mkt.symbols.items():
            if meta["asset_class"] not in ("equity", "etf"):
                continue
            key = f"{sym}_C"
            if key in portfolio.positions:
                continue
            bars = mkt.bars_through(sym, i)
            vol = realized_vol(bars, 20)
            if not vol or len(bars) < 21:
                continue
            px = bars[-1].close
            strike = round(px * 1.05, 0)
            prem = black_scholes(px, strike, 7, max(0.12, vol * 1.2), "call")
            if prem <= 0.02:
                continue
            out.append(OrderProposal(
                symbol=key, asset_class="option", side="buy", price=prem,
                stop=prem * 0.5, target=prem * 2.0, multiplier=100,
                dte=7, defined_risk=True, minutes_since_open=30,
                thesis="chase the weekly target",
                meta={"underlying": sym, "strike": strike, "kind": "call",
                      "iv": max(0.12, vol * 1.2), "expiry_index": i + 7}))
        return out


class WithoutTarget(Strategy):
    """D-24 study wrapper: the same entries, with the target removed.

    Exits then come only from the stop, a halt, or `max_holding_days`. Used by
    sim/target_ablation.py to compare against the same strategy's own 2R
    target on identical markets. Not in ALL, so the default suite is unchanged.
    """

    def __init__(self, base: Strategy):
        self.base = base
        self.name = f"{base.name}_no_target"

    def propose(self, mkt, i, portfolio, cfg):
        out = self.base.propose(mkt, i, portfolio, cfg)
        for p in out:
            p.target = None
        return out


ALL = {s.name: s for s in [TrendPullback(), MomentumBreakout(), OptionSwing(),
                           GraduatedSwing(), TargetChaser()]}
