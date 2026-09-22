#!/usr/bin/env python3
"""The proxy study, repeated every year, because one year decided nothing.

`tools/proxy_study.py` asked whether any signal-time feature separates the
breakouts that never pull back from the ones that do, and concluded no: in
2026 breakout_% predicted the LABEL strongly (12% -> 47%) while the top
quintile's return stayed at baseline, because within the no-pullback group the
same feature predicted return NEGATIVELY and the two effects cancelled.

That was 2026 alone. The multi-year entry study has since shown 2026 to be the
one year out of six that behaved differently, so the negative result has to be
re-tested before it is trusted — and so does its opposite.

The statistic that matters is NOT the pooled top-quintile return. It is whether
the Q5-Q1 spread in chase return keeps the SAME SIGN year after year. A feature
that helps in four years and hurts in two is not a filter, whatever its pooled
average says.

    python3 -m tools.multiproxy --years 2021 2022 2023 2024 2025 2026
"""
import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.pit_study import CACHE
from tools import proxy_study
from tools.proxy_study import FEATURES


def q_split(rows, feat, k=5):
    rows = sorted(rows, key=lambda r: r[feat])
    n = len(rows) // k
    return [rows[q * n:(q + 1) * n] if q < k - 1 else rows[(k - 1) * n:]
            for q in range(k)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+",
                    default=[2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--wait", type=int, default=5)
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    print(f"loading {CACHE} ...", flush=True)
    blob = json.load(gzip.open(CACHE, "rt"))

    by_year = {}
    for y in a.years:
        rows = proxy_study.run(y, a.wait, a.top, a.horizon, blob=blob)
        if rows:
            by_year[y] = rows
        npb = sum(r["no_pullback"] for r in rows) / len(rows) if rows else 0
        print(f"  {y}: {len(rows):>5} signals, {npb:.0%} never pulled back",
              flush=True)

    yrs = sorted(by_year)
    out = {}
    for feat in FEATURES:
        print(f"\n=== {feat} — {FEATURES[feat]} ===")
        print(f"{'year':<7}{'Q1 R':>9}{'Q5 R':>9}{'Q5-Q1':>9}"
              f"{'Q1 noPB%':>10}{'Q5 noPB%':>10}{'base R':>9}")
        spreads, lab_spreads = [], []
        for y in yrs:
            qs = q_split(by_year[y], feat)
            r1 = statistics.mean(r["chase_R"] for r in qs[0])
            r5 = statistics.mean(r["chase_R"] for r in qs[-1])
            l1 = statistics.mean(r["no_pullback"] for r in qs[0])
            l5 = statistics.mean(r["no_pullback"] for r in qs[-1])
            base = statistics.mean(r["chase_R"] for r in by_year[y])
            spreads.append(r5 - r1)
            lab_spreads.append(l5 - l1)
            print(f"{y:<7}{r1:>+9.3f}{r5:>+9.3f}{r5 - r1:>+9.3f}"
                  f"{l1:>10.0%}{l5:>10.0%}{base:>+9.3f}")
        pos = sum(1 for s in spreads if s > 0)
        sd = statistics.stdev(spreads) if len(spreads) > 1 else 0.0
        se = sd / len(spreads) ** 0.5 if sd else 0.0
        t = statistics.mean(spreads) / se if se else 0.0
        print(f"{'ALL':<7}{'':>9}{'':>9}{statistics.mean(spreads):>+9.3f}"
              f"   return spread positive in {pos}/{len(spreads)} years, "
              f"t={t:+.1f}")
        print(f"{'':<7}{'':>9}{'':>9}{statistics.mean(lab_spreads):>+9.3f}"
              f"   LABEL spread (no-pullback rate), for contrast")
        out[feat] = {"spreads": spreads, "years": yrs, "t": t,
                     "positive_years": pos,
                     "label_spreads": lab_spreads}

    print("\n=== summary: a filter needs a spread that keeps its sign ===")
    print(f"{'feature':<16}{'mean Q5-Q1 R':>14}{'t':>7}{'consistent':>12}"
          f"{'label Q5-Q1':>13}")
    for feat, d in sorted(out.items(), key=lambda kv: -abs(kv[1]["t"])):
        n = len(d["spreads"])
        consistent = f"{d['positive_years']}/{n}"
        print(f"{feat:<16}{statistics.mean(d['spreads']):>+14.3f}{d['t']:>7.1f}"
              f"{consistent:>12}{statistics.mean(d['label_spreads']):>+13.2f}")

    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, default=str))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
