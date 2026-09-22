#!/usr/bin/env python3
"""Run the entry and target studies across every available year at once.

Everything decided so far rests on one year of data — 2026 — where the best
result was chase +0.054R at t=+1.1 and retest +0.092R at t=+1.7. Neither is
significant. A t of 1.7 on a single sample is exactly what a strategy with no
edge produces about one time in ten, and we have been choosing between arms on
differences smaller than that.

This re-runs the same code year by year so the question becomes the only one
that matters: does the ranking HOLD, or does each year pick a different winner?
A rule that wins in 2022 and 2026 but loses in 2023 and 2024 is not a rule.

    python3 -m tools.multiyear --years 2021 2022 2023 2024 2025 2026

Caveat that grows with distance: the universe is built from /v2/assets as it
stands TODAY, so names delisted before today are absent entirely. That biases
every year upward, and it biases the early years MORE, because more of their
names have since died. Treat a decaying edge as partly an artifact; treat an
edge that grows into the past as suspicious for the same reason.
"""
import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.pit_study import CACHE
from tools.target_study import summarise
from tools import entry_study


def pooled(rows):
    """Combine per-year trade lists into one sample."""
    out = []
    for r in rows:
        out.extend(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+",
                    default=[2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--wait", type=int, default=5)
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    print(f"loading {CACHE} ...", flush=True)
    blob = json.load(gzip.open(CACHE, "rt"))
    print(f"  {len(blob['bars'])} symbols", flush=True)

    per_year, collected = {}, {"chase": [], "retest": [], "missed": []}
    hdr = (f"{'year':<7}{'sig':>7}{'arm':>9}{'taken':>7}{'fill%':>7}"
           f"{'expect':>9}{'+/-SE':>8}{'t':>7}{'totalR':>9}{'win%':>7}")
    print("\n" + hdr)
    print("-" * len(hdr))

    for y in a.years:
        r = entry_study.run(y, a.horizon, a.wait, a.top, blob=blob)
        if not r["signals"]:
            print(f"{y:<7}{0:>7}   (no signals — year not in the data)")
            continue
        per_year[y] = {}
        for arm in ("chase", "retest"):
            s = summarise(r["rows"][arm])
            if not s["n"]:
                continue
            per_year[y][arm] = s
            collected[arm].append(r["rows"][arm])
            print(f"{y:<7}{r['signals']:>7}{arm:>9}{s['n']:>7}"
                  f"{s['n'] / r['signals']:>7.0%}{s['expectancy']:>9.3f}"
                  f"{s['se']:>8.3f}{s['t']:>7.1f}{s['total_R']:>9.1f}"
                  f"{s['win_rate']:>7.0%}")
        collected["missed"].append(r["missed"])
        m = summarise(r["missed"])
        if m["n"]:
            per_year[y]["missed"] = m
            print(f"{'':<7}{'':>7}{'missed':>9}{m['n']:>7}{'':>7}"
                  f"{m['expectancy']:>9.3f}{m['se']:>8.3f}{m['t']:>7.1f}"
                  f"{m['total_R']:>9.1f}{m['win_rate']:>7.0%}")
        print("-" * len(hdr))

    if not per_year:
        print("no years produced signals")
        return 1

    # ---- pooled: the whole point. n grows, SE shrinks as 1/sqrt(n).
    print("\n=== pooled across all years ===")
    print(f"{'arm':<9}{'taken':>8}{'expect':>9}{'+/-SE':>8}{'t':>7}"
          f"{'totalR':>9}{'win%':>7}{'avgW':>7}{'avgL':>7}")
    pool = {}
    for arm in ("chase", "retest", "missed"):
        s = summarise(pooled(collected[arm]))
        if not s["n"]:
            continue
        pool[arm] = s
        print(f"{arm:<9}{s['n']:>8}{s['expectancy']:>9.3f}{s['se']:>8.3f}"
              f"{s['t']:>7.1f}{s['total_R']:>9.1f}{s['win_rate']:>7.0%}"
              f"{s['avg_win']:>7.2f}{s['avg_loss']:>7.2f}")

    # ---- consistency: does the same arm win every year?
    yrs = [y for y in per_year if "chase" in per_year[y] and "retest" in per_year[y]]
    if yrs:
        wins = [y for y in yrs if per_year[y]["retest"]["expectancy"]
                > per_year[y]["chase"]["expectancy"]]
        print(f"\nretest beat chase on expectancy in {len(wins)}/{len(yrs)} "
              f"years: {wins or 'none'}")
        # Sign test: under no difference, each year is a coin flip.
        k, n = len(wins), len(yrs)
        from math import comb
        p = sum(comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n * 2
        print(f"two-sided sign test p = {min(p, 1.0):.3f} "
              f"({'not ' if p > 0.05 else ''}significant at 0.05)")
        diffs = [per_year[y]["retest"]["expectancy"]
                 - per_year[y]["chase"]["expectancy"] for y in yrs]
        print(f"per-year edge (retest - chase): "
              f"{', '.join(f'{y}:{d:+.3f}' for y, d in zip(yrs, diffs))}")
        if len(diffs) > 1:
            sd = statistics.stdev(diffs)
            se = sd / len(diffs) ** 0.5
            print(f"mean {statistics.mean(diffs):+.3f}  sd {sd:.3f}  "
                  f"t {statistics.mean(diffs) / se if se else 0:+.1f} "
                  f"(paired across years, n={len(diffs)})")

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"per_year": per_year, "pooled": pool,
             "params": {"horizon": a.horizon, "wait": a.wait, "top": a.top}},
            indent=2, default=str))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
