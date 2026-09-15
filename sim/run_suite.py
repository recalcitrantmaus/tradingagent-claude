#!/usr/bin/env python3
"""Monte Carlo the strategies against the risk engine and report.

    python3 -m sim.run_suite --seeds 200 --days 260
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import replace

from engine.config import RiskConfig, DEFAULT
from engine.market import SyntheticMarket
from engine.sim import run
from engine.strategies import ALL
from sim.universe import UNIVERSE


def aggregate(results):
    fin = [r.final_equity for r in results]
    wk = [w for r in results for w in r.weekly_returns]
    return {
        "runs": len(results),
        "median_final_equity": round(statistics.median(fin), 2),
        "mean_final_equity": round(statistics.mean(fin), 2),
        "p10_final_equity": round(sorted(fin)[len(fin) // 10], 2),
        "p90_final_equity": round(sorted(fin)[min(len(fin) - 1, 9 * len(fin) // 10)], 2),
        "median_total_return": round(statistics.median([r.total_return for r in results]), 4),
        "pct_runs_profitable": round(sum(1 for r in results if r.total_return > 0) / len(results), 3),
        "pct_runs_ruined_50pct": round(sum(1 for r in results if r.ruined) / len(results), 3),
        "pct_runs_locked": round(sum(1 for r in results if r.end_state == "LOCKED") / len(results), 3),
        "mean_weekly_return": round(statistics.mean(wk), 5) if wk else None,
        "median_weekly_return": round(statistics.median(wk), 5) if wk else None,
        "stdev_weekly_return": round(statistics.pstdev(wk), 5) if wk else None,
        "pct_weeks_over_+5pct": round(sum(1 for w in wk if w >= 0.05) / len(wk), 3) if wk else None,
        "mean_max_drawdown": round(statistics.mean([r.max_drawdown for r in results]), 4),
        "worst_max_drawdown": round(max(r.max_drawdown for r in results), 4),
        "mean_trades": round(statistics.mean([r.trades for r in results]), 1),
        "mean_win_rate": round(statistics.mean([r.win_rate for r in results]), 3),
        "mean_fees_paid": round(statistics.mean([r.fees_paid for r in results]), 2),
        "fees_as_pct_of_start": round(
            statistics.mean([r.fees_paid for r in results]) / DEFAULT.starting_equity, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--days", type=int, default=260)
    ap.add_argument("--out", default="sim/results/suite.json")
    ap.add_argument("--no-guardrails", action="store_true",
                    help="disable circuit breakers, for the ablation study")
    ap.add_argument("--options-at-300", action="store_true",
                    help="keep all guardrails but drop the option equity floor, "
                         "isolating what that one rule contributes")
    args = ap.parse_args()

    cfg = DEFAULT
    if args.no_guardrails:
        cfg = RiskConfig(
            max_risk_per_trade_pct=0.50, max_position_pct_equity=1.0,
            max_position_pct_option=1.0, max_position_pct_crypto=1.0,
            daily_loss_halt_pct=9.9, weekly_loss_halt_pct=9.9,
            max_drawdown_lock_pct=9.9, consecutive_loss_halt=10_000,
            min_cash_reserve_pct=0.0, option_min_dte=0, option_min_equity=0.0,
            max_option_contracts_under_1k=100, max_concurrent_positions=8,
            class_caps={"equity": 1.0, "etf": 1.0, "option": 1.0, "crypto": 1.0})

    if args.options_at_300:
        cfg = replace(DEFAULT, option_min_equity=0.0)

    label = ("no_guardrails" if args.no_guardrails
             else "options_at_300" if args.options_at_300 else "default")
    report = {"config": label,
              "days": args.days, "seeds": args.seeds, "strategies": {}}

    for name, strat in ALL.items():
        results = []
        for seed in range(args.seeds):
            mkt = SyntheticMarket(UNIVERSE, args.days, seed=seed)
            results.append(run(strat, mkt, cfg, seed=seed))
        report["strategies"][name] = aggregate(results)
        rej = {}
        for r in results:
            for k, v in r.rejections.items():
                rej[k] = rej.get(k, 0) + v
        report["strategies"][name]["top_rejections"] = dict(
            sorted(rej.items(), key=lambda kv: -kv[1])[:5])
        print(f"  {name:26s} median ${report['strategies'][name]['median_final_equity']:>8.2f}"
              f"  ruin {report['strategies'][name]['pct_runs_ruined_50pct']:.1%}"
              f"  wk {report['strategies'][name]['mean_weekly_return'] or 0:+.3%}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
