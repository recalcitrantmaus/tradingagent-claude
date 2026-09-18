# D-24: which target definition? — forward test on 2026

**Answer: none of them. Targets destroy expectancy in this strategy, and the
rules-based structural target — the one recommended on 2026-09-18 — is the
worst of the options tested.**

Run it yourself:

```
python3 -m tools.target_study --year 2026 --horizon 20
```

## Method

1,983 twenty-day breakout signals across the committed 150-name universe,
2026-01-02 to 2026-09-18, forward-tested on real daily bars.

- Signal on `close[i] > max(high[i-20:i])` — the same test `tools.screen` uses.
- **Entry at `open[i+1]`.** You cannot buy the close you screened on, and this
  reproduces the overnight gap where the R gate actually binds.
- Stop `max(entry - 1.5*ATR, entry*0.92)` — the constitution's mandatory stop.
- Everything feeding a target comes from `bars[:i+1]` only. A swing high must
  be **confirmed** by bar `i` (its right-hand window closed), or the study
  reads the future and every number is a lie.
- Resolution walks forward to the horizon: a stop fills at `min(stop, open)`
  so a gap through it is worse than −1R; a target fills at `max(target, open)`;
  if both are touched in one bar the **stop** is assumed first, because
  intraday order is unknowable from daily bars.
- The 1.5R gate is applied to expected R at entry, exactly as `engine/risk.py`
  applies it.

## Results, 20-day horizon

| target | taken | %sig | expectancy | ±SE | t | total R | win% | avg W | avg L |
|---|---|---|---|---|---|---|---|---|---|
| mechanical (`entry + 3*ATR`) | 1983 | 100% | +0.032 | 0.034 | +0.9 | +62.9 | 37% | +1.91 | −1.05 |
| structural (swing/MA200/round) | 185 | 9% | **−0.226** | 0.121 | −1.9 | −41.8 | 27% | +2.25 | −1.14 |
| structural, coarse round numbers | 544 | 27% | +0.079 | 0.080 | +1.0 | +43.0 | 33% | +2.45 | −1.07 |
| structural, swing highs only | 1050 | 53% | +0.050 | 0.047 | +1.1 | +52.7 | 36% | +1.98 | −1.05 |
| structural, 200-day only | 1830 | 92% | +0.039 | 0.035 | +1.1 | +70.9 | 37% | +1.91 | −1.05 |
| structure as *filter*, no target | 185 | 9% | −0.146 | 0.153 | −1.0 | −27.0 | 24% | +2.93 | −1.13 |
| **none** (stop or 20-day time stop) | 1983 | 100% | **+0.132** | 0.049 | **+2.7** | **+261.8** | 31% | +2.70 | −1.04 |

**Only `none` is distinguishable from zero.** Every other arm sits inside one
or two standard errors. Reading a ranking among them would be reading noise.

## Why the structural target fails, mechanically

It is not a tuning problem. Decomposing which level ends up nearest:

| level | how often it binds | median distance | clears the 1.5R gate |
|---|---|---|---|
| round number | 68% | 0.55R | 17% |
| swing high | 30% | **0.41R** | **14%** |
| 200-day MA | 2% | 1.65R | 53% |

Two findings there. First, the fine round-number grid (every $1 at $34) was
doing most of the work, and that is arithmetic, not resistance — coarsening it
lifts expectancy from −0.226 to +0.079. But second, and decisively: **swing
highs sit even closer, at a median 0.41R.**

That is not a flaw in the rule, it is what a breakout *is*. Closing above the
20-day high means arriving exactly where overhead supply begins. Demanding
1.5R of clear air above a fresh breakout is close to demanding the setup not
be a breakout — it fires on 9% of signals, and the 9% it selects are worse than
average, not better.

**Structure is a bad exit AND a bad entry filter here.** The `structural_filter`
arm tests them separately — gate on structure, then run with no target — and it
is still negative, getting worse as the horizon lengthens (−0.15 at 20 days,
−0.54 at 40, −0.65 at 60). It anti-selects.

## Horizon sensitivity — and the one thing that is fragile

Expectancy by holding horizon:

| arm | 10d | 20d | 40d | 60d |
|---|---|---|---|---|
| mechanical | +0.027 | +0.032 | +0.005 | +0.005 |
| structural | −0.237 | −0.226 | −0.324 | −0.332 |
| struct_coarse | +0.027 | +0.079 | −0.076 | −0.093 |
| struct_swing | +0.063 | +0.050 | +0.025 | +0.017 |
| struct_ma200 | +0.028 | +0.039 | +0.005 | +0.004 |
| structure-as-filter | −0.192 | −0.146 | −0.537 | −0.648 |
| **none** | +0.047 | **+0.132** | +0.084 | **−0.038** |

`none` is best at 10, 20 and 40 days and **turns negative at 60**. "Let winners
run" is not the finding. **"Let winners run, with a time stop around 20 days"**
is the finding, and the time stop is load-bearing — without it the edge decays
to nothing as losers that never hit the stop bleed out.

## Regime dependence — every arm is negative in Q3

| arm | Q1 | Q2 | Q3 |
|---|---|---|---|
| mechanical | +0.195 (782) | +0.034 (727) | −0.241 (474) |
| struct_coarse | +0.280 (298) | +0.061 (156) | −0.556 (90) |
| struct_swing | +0.204 (536) | +0.043 (341) | −0.411 (173) |
| none | +0.256 (782) | +0.285 (727) | −0.307 (474) |

**There is no target definition that survives Q3 2026.** Whatever changed in
the third quarter, it broke breakout trading in this universe across every
exit rule tested. A strategy that is positive in Q1–Q2 and negative in Q3 is
not a strategy with an edge, it is a strategy with a regime — and the account
has no regime detector.

## What this does not measure, stated plainly

- **Survivorship.** `data/universe.json` was built on prices as of 2026-09-17
  filtered to $3–$75. A stock that was $40 in January and is $200 now was
  excluded — and those are precisely the trades a breakout strategy lives on.
  This **understates the right tail**, which penalises `none` more than any
  other arm, since `none` is the arm that depends on it. The true gap is
  probably wider, not narrower.
- **Costs.** Gross R. At a $35 entry with ~$2.77 of risk per share, 5bps each
  way is roughly **0.013R per trade** — about 10% of `none`'s edge and about
  40% of `mechanical`'s.
- **Position limits.** Every signal is taken independently. The live account
  holds at most 4 at once, so it samples this distribution and adds variance.
- **One year, one universe, one strategy.** 2026 only.

## What follows

1. **Do not adopt a structural target.** It fails as a target, fails as a
   filter, fails at every horizon, and the failure is structural rather than
   parametric.
2. **The live question becomes the exit, not the target.** `require_target`
   and `min_expected_r` currently make a target mandatory, so today's config
   cannot express the only arm with a measurable edge. That is a real decision
   and it changes `engine/config.py`, so it needs its own evidence trail.
3. **Nothing here licenses removing the stop.** The stop is what makes −1.05R
   the average loss. Every arm above depends on it.
4. **Q3 is the open question.** Before trusting any of this, find out whether
   Q3 is a regime the account can detect in advance, or one it can only
   discover by losing money in it.
