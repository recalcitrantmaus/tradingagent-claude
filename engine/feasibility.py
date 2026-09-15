"""Is 5% per week reachable? Answer it with arithmetic, not opinion.

Two questions:
  1. What does the target compound to? (sanity)
  2. Given a realistic edge, what fraction of a bet must be risked to have a
     coin's chance of hitting +5% in a week -- and what does that do to the
     probability of ruin over a year?

This module exists so the agent can re-derive the answer rather than take it
on faith, and so the answer updates if the account's real statistics change.
"""

from dataclasses import dataclass
from typing import List
import math
import random
import statistics


def compounded(weekly_rate: float, weeks: int, start: float) -> float:
    return start * (1 + weekly_rate) ** weeks


@dataclass
class KellySim:
    win_rate: float
    win_multiple: float      # R won on a winner
    loss_multiple: float     # R lost on a loser (usually 1.0)
    trades_per_week: int

    def edge_per_trade_R(self) -> float:
        return (self.win_rate * self.win_multiple
                - (1 - self.win_rate) * self.loss_multiple)

    def kelly_fraction(self) -> float:
        b = self.win_multiple / self.loss_multiple
        p = self.win_rate
        f = (p * (b + 1) - 1) / b
        return max(0.0, f)

    def risk_needed_for(self, weekly_target: float) -> float:
        """Fraction of equity to risk per trade to make the target the
        *expected* weekly return. Ignores compounding drag, so it is
        optimistic by construction."""
        e = self.edge_per_trade_R()
        if e <= 1e-9:
            return float("inf")   # no edge: no amount of sizing gets you there
        return weekly_target / (e * self.trades_per_week)

    def monte_carlo(self, risk_frac: float, weeks: int, trials: int = 5000,
                    seed: int = 7) -> dict:
        rng = random.Random(seed)
        finals, ruins, hit_weeks, total_weeks = [], 0, 0, 0
        for _ in range(trials):
            eq = 1.0
            for _w in range(weeks):
                wk_start = eq
                for _t in range(self.trades_per_week):
                    stake = eq * risk_frac
                    if rng.random() < self.win_rate:
                        eq += stake * self.win_multiple
                    else:
                        eq -= stake * self.loss_multiple
                    if eq <= 0.05:
                        eq = 0.0
                        break
                total_weeks += 1
                if wk_start > 0 and eq / wk_start - 1 >= 0.05:
                    hit_weeks += 1
                if eq == 0.0:
                    break
            finals.append(eq)
            if eq <= 0.5:
                ruins += 1
        finals.sort()
        return {
            "risk_per_trade": round(risk_frac, 4),
            "median_final_multiple": round(statistics.median(finals), 4),
            "mean_final_multiple": round(statistics.mean(finals), 4),
            "p05_final_multiple": round(finals[trials // 20], 4),
            "p95_final_multiple": round(finals[-trials // 20], 4),
            "prob_lose_half_or_more": round(ruins / trials, 4),
            "prob_total_loss": round(sum(1 for f in finals if f == 0.0) / trials, 4),
            "pct_weeks_hitting_+5pct": round(hit_weeks / total_weeks, 4),
        }


def target_reality_check(start: float = 300.0, weekly: float = 0.05) -> dict:
    return {
        "start": start,
        "weekly_target": weekly,
        "after_4_weeks": round(compounded(weekly, 4, start), 2),
        "after_26_weeks": round(compounded(weekly, 26, start), 2),
        "after_52_weeks": round(compounded(weekly, 52, start), 2),
        "annualized": round((1 + weekly) ** 52 - 1, 2),
        "after_3_years": round(compounded(weekly, 156, start), 2),
    }


def edge_sensitivity(weekly_target: float = 0.05, weeks: int = 52,
                     trades_per_week: int = 5) -> List[dict]:
    """The whole feasibility question reduces to one unmeasured number: edge.

    Every 'can I make 5% a week' answer is really an answer about expected R
    per trade. Published retail results cluster at or below zero after costs,
    so this sweep runs from clearly-negative to implausibly-good and reports
    what each implies. Do not read the top rows as achievable; read them as
    the price of admission.
    """
    rows = []
    for win_rate in (0.35, 0.40, 0.45, 0.50, 0.55):
        for win_multiple in (1.0, 1.5, 2.0):
            k = KellySim(win_rate, win_multiple, 1.0, trades_per_week)
            e = k.edge_per_trade_R()
            need = k.risk_needed_for(weekly_target)
            row = {
                "win_rate": win_rate,
                "reward_to_risk": win_multiple,
                "edge_R_per_trade": round(e, 4),
                "kelly_fraction": round(k.kelly_fraction(), 4),
                "risk_per_trade_needed_for_target": (
                    None if need == float("inf") else round(need, 4)),
                "target_reachable_within_kelly": (
                    need != float("inf") and need <= k.kelly_fraction()),
            }
            if need != float("inf"):
                row["mc_at_needed_risk"] = k.monte_carlo(min(need, 0.95), weeks)
            row["mc_at_policy_risk_2pct"] = k.monte_carlo(0.02, weeks)
            rows.append(row)
    return rows
