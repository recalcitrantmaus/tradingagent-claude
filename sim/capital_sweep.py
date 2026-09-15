#!/usr/bin/env python3
"""Does more starting capital actually help, and where does it stop mattering?

At $300 a 2% risk budget is $6. After the stop distance and whole-share
rounding, many correct signals cannot be expressed at all — the account is
too small to hold its own opinion. This sweep measures that directly:

  zero_size_rate  share of approved-on-merit proposals killed by rounding
  mean_qty        average position size in shares/contracts (resolution)
  option_trades   whether the option sleeve is reachable at all

Run:  python3 -m sim.capital_sweep
"""
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.market import SyntheticMarket
from engine.sim import run
from engine.strategies import ALL
from sim.universe import UNIVERSE

LEVELS = [300, 500, 750, 1000, 1500, 2500, 5000, 10000]
STRATEGIES = ["trend_pullback", "momentum_breakout", "option_swing"]


def main(seeds: int = 150, days: int = 260):
    out = {"seeds": seeds, "days": days, "levels": {}}
    print(f"{'equity':>8} {'strategy':22} {'median ret':>11} {'%profit':>8} "
          f"{'trades':>7} {'mean qty':>9} {'rounded-out':>12} {'opt trades':>11}")
    for eq in LEVELS:
        cfg = replace(DEFAULT, starting_equity=float(eq))
        out["levels"][eq] = {}
        for name in STRATEGIES:
            results = []
            for seed in range(seeds):
                mkt = SyntheticMarket(UNIVERSE, days, seed=seed)
                results.append(run(ALL[name], mkt, cfg, seed=seed))
            row = {
                "median_total_return": round(
                    statistics.median([r.total_return for r in results]), 4),
                "pct_profitable": round(
                    sum(1 for r in results if r.total_return > 0) / len(results), 3),
                "mean_trades": round(statistics.mean([r.trades for r in results]), 1),
                "mean_entry_qty": round(
                    statistics.mean([r.mean_entry_qty for r in results]), 2),
                "zero_size_rate": round(
                    statistics.mean([r.zero_size_rate for r in results]), 3),
                "mean_option_trades": round(
                    statistics.mean([r.option_trades for r in results]), 2),
                "pct_ruined": round(
                    sum(1 for r in results if r.ruined) / len(results), 3),
                "mean_max_drawdown": round(
                    statistics.mean([r.max_drawdown for r in results]), 4),
            }
            out["levels"][eq][name] = row
            print(f"{eq:>8} {name:22} {row['median_total_return']:>10.2%} "
                  f"{row['pct_profitable']:>8.1%} {row['mean_trades']:>7.1f} "
                  f"{row['mean_entry_qty']:>9.2f} {row['zero_size_rate']:>11.1%} "
                  f"{row['mean_option_trades']:>11.2f}")
        print()
    Path("sim/results/capital_sweep.json").write_text(json.dumps(out, indent=2))
    print("wrote sim/results/capital_sweep.json")


if __name__ == "__main__":
    main()
