#!/usr/bin/env python3
"""D-24: does removing the target improve outcomes without worsening ruin?

    python3 -m sim.target_ablation --seeds 300
    python3 -m sim.target_ablation --seeds 3000

CLAUDE.md's bar for changing a rule is "a backtest showing a better median
outcome without a worse ruin rate". Each arm runs on the SAME synthetic market
per seed, so the comparison is paired: the per-seed difference in final equity
measures the rule, not the luck of the draw.

Arms, per strategy:
  target_2R       today's rule: target = entry + 3 ATR against a 1.5 ATR stop,
                  half scaled out at the target, rest to breakeven
  no_target_Nd    the same entries with no target; exit on the stop, a halt,
                  or after N business days held
  no_target_none  no target and no time stop (reference only)
"""
import argparse
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.market import SyntheticMarket
from engine.sim import run
from engine.strategies import ALL, WithoutTarget
from sim.run_suite import aggregate
from sim.universe import UNIVERSE

STRATEGIES = ("momentum_breakout", "trend_pullback")
HORIZONS = (10, 20, 40)


def arms(name):
    base = ALL[name]
    out = {"target_2R": (base, DEFAULT)}
    for n in HORIZONS:
        out[f"no_target_{n}d"] = (
            WithoutTarget(base),
            replace(DEFAULT, require_target=False, max_holding_days=n))
    out["no_target_none"] = (
        WithoutTarget(base), replace(DEFAULT, require_target=False))
    return out


def paired(base_fin, arm_fin):
    diffs = [a - b for a, b in zip(arm_fin, base_fin)]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    se = sd / len(diffs) ** 0.5 if sd else 0.0
    return {
        "mean_diff_vs_target": round(mean, 3),
        "t_vs_target": round(mean / se, 2) if se else None,
        "pct_seeds_better": round(sum(1 for d in diffs if d > 0) / len(diffs), 3),
        "pct_seeds_worse": round(sum(1 for d in diffs if d < 0) / len(diffs), 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--days", type=int, default=260)
    ap.add_argument("--out", default="sim/results/target_ablation.json")
    args = ap.parse_args()

    report = {"seeds": args.seeds, "days": args.days, "strategies": {}}
    for name in STRATEGIES:
        results = {}
        for arm, (strat, cfg) in arms(name).items():
            results[arm] = [run(strat, SyntheticMarket(UNIVERSE, args.days, seed=s),
                                cfg, seed=s) for s in range(args.seeds)]
        base_fin = [r.final_equity for r in results["target_2R"]]
        rows = {}
        for arm, rs in results.items():
            agg = aggregate(rs)
            reasons = {}
            for r in rs:
                for k, v in r.exit_reasons.items():
                    reasons[k] = reasons.get(k, 0) + v
            agg["exit_reasons"] = reasons
            agg["mean_R"] = round(statistics.mean(
                [x for r in rs for x in r.realized_R]), 4) if any(
                r.realized_R for r in rs) else None
            if arm != "target_2R":
                agg.update(paired(base_fin, [r.final_equity for r in rs]))
            rows[arm] = agg
            print(f"  {name:18s} {arm:15s} median ${agg['median_final_equity']:>8.2f}"
                  f"  mean ${agg['mean_final_equity']:>8.2f}"
                  f"  ruin {agg['pct_runs_ruined_50pct']:.1%}"
                  f"  locked {agg['pct_runs_locked']:.1%}"
                  f"  worstDD {agg['worst_max_drawdown']:.1%}"
                  f"  meanR {agg['mean_R'] if agg['mean_R'] is not None else 'n/a'}"
                  + (f"  t {agg['t_vs_target']}" if arm != "target_2R" else ""))
        report["strategies"][name] = rows

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
