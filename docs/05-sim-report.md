# Phase 1 simulation report

**What was simulated:** 300 independent one-year paths (260 sessions) per
strategy, per configuration, on the synthetic market in `engine/market.py`.
Reproduce with:

```
python3 -m sim.run_suite --seeds 300 --days 260
python3 -m sim.run_suite --seeds 300 --days 260 --options-at-300
python3 -m sim.run_suite --seeds 300 --days 260 --no-guardrails
python3 -m unittest discover -s tests
```

**What this is not:** a backtest. Every market-data host is blocked in this
environment (`docs/03-environment-constraints.md`), so these are synthetic
paths — regime-switching drift and vol, 2% daily jump probability, fat tails,
and a common beta factor so a crisis hits everything at once. The numbers
below are evidence about **the risk machinery**, not forecasts of returns.

Honesty modelling: entries fill at the *next* open, never at the signal
price; if a bar touches both stop and target the **stop** is assumed first;
options are repriced daily with Black-Scholes on the live underlying with
theta; every fill pays spread/slippage, and options pay per-contract fees.
(Note: for equities, friction is modelled as a price concession inside the
fill, so it shows up in returns rather than in the `fees_paid` column — a
`$0.00` fee figure for stocks does not mean trading was free.)

---

## Result 1 — With the full constitution, nothing blows up

| Strategy | Median final | P10 | P90 | % runs profitable | % ruined | Mean weekly | Weeks ≥ +5% | Worst DD |
|---|---|---|---|---|---|---|---|---|
| trend_pullback | $302.17 | $286.51 | $328.02 | 56.3% | 0% | +0.033% | 0.1% | 12.9% |
| momentum_breakout | $308.89 | $274.07 | $352.68 | 60.3% | 0% | +0.067% | 0.6% | 21.1% |
| option_swing | $300.00 | — | — | — | 0% | 0% | 0% | 0% |
| target_chaser (control) | $300.00 | — | — | — | 0% | 0% | 0% | 0% |

Read this honestly: **the guardrails work and the returns are unremarkable.**
A median of +0.7% to +3.0% per year is roughly a coin flip after costs. The
5%/week target was hit in **0.1%-0.6% of weeks**, against a target that
requires hitting it in most of them.

The two option strategies show `$300.00` flat because they were **rejected on
every attempt** — 9,498 rejections in the smoke run, all reading *"size rounds
to zero"* or *"equity below option floor"*. That is the finding in Result 2.

## Result 2 — Options are unaffordable at $300, and this was discovered, not assumed

The first suite produced a suspicious result: `option_swing` executed **1.0
trade per 300 sessions**. Investigation of the rejection log showed it was not
a bug:

> 2% of $300 = **$6** of risk budget. One contract at a $2.00 premium with the
> policy 40% stop risks **$80**. `int(6/80) = 0`.

For one contract to fit, equity must exceed `2000 x premium`, i.e. roughly
**$1,500** for the cheapest liquid contracts.

**Remediation:** `RiskConfig.option_min_equity = 1500`, enforced in
`RiskOfficer.evaluate` and pinned by `test_options_blocked_below_equity_floor`.
The agent now says *why* it cannot trade options instead of silently
generating proposals that die in the sizing step. The first milestone for the
account is therefore $1,500, not a weekly percentage.

## Result 3 — The chase-the-target control locks the account 100% of the time

Isolating the option floor (`--options-at-300`: every other guardrail on):

| Strategy | Median final | % runs ending LOCKED | Mean weekly | Win rate | Mean max DD |
|---|---|---|---|---|---|
| option_swing | $300.00 | 0.3% | -0.05% | 24.8% | 3.2% |
| target_chaser (control) | **$233.36** | **100%** | -0.468% | **3.2%** | 22.6% |

`target_chaser` is the deliberately reckless control — 7-DTE, 5% OTM calls,
sized to reach the weekly target. It won **3.2%** of its trades and **every
single one of 300 runs hit the -20% drawdown lock.** The circuit breaker
caught all 300 and stopped the bleeding at -22%.

This is the clearest evidence in the report: the strategy that most directly
pursues *"5% per week"* is the strategy the risk engine has to shut down.

## Result 4 — Ablation: what the guardrails are actually worth

Same strategies, same 300 seeds, all circuit breakers and sizing caps removed:

| Strategy | Median final | P10 | % ruined (≥50% loss) | Worst DD | Weeks ≥ +5% |
|---|---|---|---|---|---|
| trend_pullback | $304.55 | $261.93 | 0% | 31.0% | 1.9% |
| momentum_breakout | $308.55 | $255.27 | 0% | 34.6% | 2.9% |
| option_swing | **$18.02** | $8.58 | **94.0%** | 99.4% | **13.3%** |
| target_chaser | **$2.27** | $1.15 | **100%** | 99.96% | 0.6% |

Two things to take from this table.

**First, the guardrails are the product.** Unrestrained option trading on
$300 destroyed 94% of accounts, with a median outcome of **$18.02** from
$300. The same strategy under the constitution ended at $300.00 having been
refused entry. Refusal was worth $282.

**Second — and this is the trap the mandate is most exposed to — unrestrained
`option_swing` hit the 5%/week target in 13.3% of weeks, versus 0.6% for the
disciplined breakout strategy.** The reckless strategy *looks better on the
stated KPI* right up until it is bankrupt. Any future tuning that optimizes
for "weeks hitting +5%" will select for exactly this behavior. **The KPI must
be compounded growth subject to survival, never the hit-rate on a weekly
target.**

## Result 5 — Sizing does not buy more winning weeks

From `engine/feasibility.py`, at a 45% win rate and 2:1 reward:risk with 5
trades a week, the share of weeks finishing ≥ +5% is **40.7% at 2% risk per
trade, 40.7% at 5%, and 40.7% at 20%.**

The reason is structural: with proportional sizing, a week clears +5%
whenever it produces 3 or more winners out of 5, at any of those risk levels.
Sizing changes the magnitude of outcomes, not the frequency of good weeks.
What it does change is the tail — at 20% per trade, **8.7% of one-year paths
end at literally zero.**

So "size up to reach the target" is not a trade-off between return and risk.
It is pure risk with no increase in the thing being targeted.

---

## What went wrong in the build, and how it was fixed

| # | Problem found | Diagnosis | Remediation |
|---|---|---|---|
| 1 | `option_swing` executed ~1 trade per year and looked broken | Not a bug: a $6 risk budget cannot fund an $80-risk contract | Added `option_min_equity = $1,500` with an explicit rejection message; test pins it |
| 2 | First feasibility run showed the 5% target as comfortably reachable | Hard-coded a 45%/2R edge — a world-class expectancy — as if it were a given | Replaced with `edge_sensitivity()` sweeping win rate and reward:risk, including the negative-edge rows that dominate the realistic prior |
| 3 | `risk_needed_for()` returned `9.0e13` at zero edge | Float comparison `e <= 0` missed values at 1e-17 | Tolerance `e <= 1e-9` returns infinity with the comment *"no edge: no amount of sizing gets you there"* |
| 4 | First ablation showed no difference from the default config | The ablation forgot to drop `option_min_equity`, so options stayed blocked in both arms and the comparison was vacuous | Ablation config now unlocks options; the 94%/100% ruin result is what that exposed |
| 5 | Broker could fail an order when slippage pushed cost above cash | Sizing happened pre-friction | `PaperBroker.execute` shaves size to what is affordable post-friction rather than erroring |
| 6 | Options sim risked flattering itself by exiting at the daily high | Intrabar ordering is unknowable from daily bars | Pessimistic convention: a bar touching both stop and target counts as a **stop** |

## What is still unproven

- **No real market data.** Every number here is synthetic. Nothing is
  validated against actual history, actual spreads, or actual option chains.
- **No LLM-in-the-loop results.** The simulated strategies are mechanical.
  They test the *guardrails*; they say nothing about whether model-generated
  theses have positive expectancy. That is what Phase 2 measures, and it is
  the question that actually decides whether this works.
- **No execution modelling of partial fills, halts, or gap-throughs.** Stops
  are assumed to fill at their level. In a real gap they will not; the
  `session-close` skill's 2x-gap check is a stand-in, not a solution.
- **The equity strategies' positive drift may be the generator's.** The
  synthetic market has a positive expected drift in bull/chop regimes, and a
  long-only strategy will harvest some of it. Treat +0.7%/yr and +3.0%/yr as
  "indistinguishable from buy-and-hold noise", not as evidence of edge.

## Recommendation before Phase 2

1. Run the 1-week paper sims on **real data with real prices**, which this
   environment cannot supply — use an environment with market-data egress, or
   a broker paper-trading sandbox (Alpaca/Tradier both provide one).
2. Measure **R per trade** from the first trade. It is the only number that
   determines whether any of this works, and it needs 30+ trades before it
   means anything.
3. Judge Phase 2 on: did the guardrails hold, were the theses traceable to
   sources, and is measured expectancy positive — **not** on whether it made
   5% in the week.

---

# Phase 1 addendum — capital sizing, and a rule I got wrong

Added 2026-09-15 in response to the question *"should the initial deposit
change, or the milestone, or both?"* Reproduce with:

```
python3 -m sim.capital_sweep
```

## Result 6 — More capital does not buy more edge

150 one-year paths at each of eight starting equity levels:

| Start | momentum_breakout median return | % profitable | mean position (shares) | proposals lost to rounding |
|---|---|---|---|---|
| $300 | **+2.75%** | 60.0% | 1.83 | 3.5% |
| $500 | +2.37% | 59.3% | 3.13 | 0.0% |
| $750 | +2.34% | 60.7% | 4.88 | 0.0% |
| $1,000 | +2.49% | 58.7% | 6.55 | 0.0% |
| $1,500 | +1.95% | 59.3% | 9.89 | 0.0% |
| $2,500 | +1.79% | 58.0% | 16.64 | 0.0% |
| $5,000 | +1.91% | 59.3% | 33.60 | 0.0% |
| $10,000 | +1.67% | 58.0% | 67.03 | 0.0% |

Two things, both of which surprised me:

1. **Percentage return is flat to slightly declining in capital.** $300 is
   not leaving returns on the table. It was the *best* row.
2. **The rounding problem is real but small, and it is gone by $500.** At
   $300, 3.5% of otherwise-valid proposals die because a $6 risk budget
   rounds to zero whole shares; by $500 that is 0.0%. The tax is about
   three percent of opportunities, not a structural handicap.

So the argument for a larger deposit is much weaker than I implied in the
Phase 1 report, where I framed $1,500 as "the point at which the instrument
set actually opens up" without checking whether opening it helped.

## Result 7 — Opening the option sleeve makes things worse at every account size

Same sweep, the option strategy, with the $1,500 equity floor respected:

| Start | option_swing median return | % profitable | option trades/yr |
|---|---|---|---|
| $1,500 | **-1.97%** | 4.0% | 8.2 |
| $2,500 | **-14.01%** | 15.3% | 38.2 |
| $5,000 | **-15.00%** | 10.7% | 31.6 |
| $10,000 | **-14.68%** | 11.3% | 28.8 |

More capital did not make options work. It bought more of a losing trade.

To check whether this was an artifact of my stop policy, I re-ran at $5,000
across five stop and target settings:

| Variant | Median return | % profitable | Win rate |
|---|---|---|---|
| policy: 40% stop / 60% target | -15.00% | 12.5% | 49.4% |
| wider 60% stop | -13.11% | 12.5% | 53.9% |
| no stop, hold to the DTE floor | -5.28% | 30.0% | 64.0% |
| tighter 25% stop | -14.35% | 17.5% | 43.8% |
| target 100% not 60% | -8.85% | 25.0% | 41.6% |

**Every variant loses.** It is not a stop-placement problem. Buying long
premium in this simulation pays an implied-vol premium on entry (IV is set at
1.15x realized) plus spread and fees on both sides, and no exit rule recovers
that. That assumption is deliberate and defensible — the variance risk
premium is a well-documented feature of real options markets, and it is the
reason systematic long-premium buying is a hard way to make money.

**Caveat, stated plainly:** this tests *one* structure — buying slightly OTM
calls. Debit spreads, which pay the premium on one leg and collect it on the
other, are a different animal and are **not** tested here. The finding is
"this repo's option strategy loses money", not "all options lose money".

## Result 8 — The fix was the wrong kind of rule, and has been replaced

The $1,500 equity floor answers *"can this account afford one contract?"* It
does not answer *"should this account be buying contracts?"* — and Result 7
says the answer to the second question is no, at every level of capital.

An equity floor alone therefore just **delays** a losing trade until the
account is big enough to lose more.

**Remediation:** the floor stays (the arithmetic behind it is still correct),
and a second gate is added. The option sleeve now requires a **measured
positive edge in the real account**:

```python
option_requires_proven_edge: bool = True
option_min_closed_trades: int = 30       # before expectancy means anything
option_min_expectancy_R: float = 0.10    # measured, from the actual fill log
```

`RiskOfficer.set_track_record()` is fed from `tools/review.py`, which computes
expectancy from `state/fills.jsonl`. The account must *earn* its way into
options with instruments that do not bleed.

Tested with `graduated_swing` — a strategy that trades stock and adds options
only once the engine unlocks them — over 150 paths per cell:

| Start | Gate | Median return | % profitable | Option trades/yr | Mean drawdown |
|---|---|---|---|---|---|
| $300 | ON | +2.75% | 60.0% | 0.00 | 9.15% |
| $300 | OFF | +2.75% | 60.0% | 0.00 | 9.15% |
| $1,500 | ON | **-0.61%** | 48.0% | 3.27 | 11.03% |
| $1,500 | OFF | -3.21% | 36.0% | 13.19 | 14.45% |
| $5,000 | ON | **-0.04%** | 50.0% | 3.47 | 11.46% |
| $5,000 | OFF | **-11.23%** | 23.3% | 25.05 | 19.69% |

At $5,000 the gate cuts option trades from 25 to 3.5 a year and improves the
median outcome by **11.2 percentage points**, with mean drawdown falling from
19.7% to 11.5%. At $300 it changes nothing, because the equity floor already
binds. It is not a blanket ban: a few trades still get through, taken by
accounts that had genuinely earned the right, and those cost little.

## Revised recommendation on capital

**Keep the $300 deposit.** The evidence does not support raising it:

- Returns do not improve with size (Result 6).
- The rounding tax at $300 is ~3.5% of proposals and vanishes by $500 — worth
  knowing, not worth funding.
- The main thing more capital unlocks is the option sleeve, and the option
  sleeve loses money (Result 7).
- $300 is the harshest honest test of whether this agent has an edge. If it
  works at $300, more capital scales it. If it does not, more capital just
  makes the lesson more expensive.

**And retire the "$1,500 milestone" framing from the Phase 1 report.** It
implied that reaching $1,500 unlocks something good. It unlocks something
this repo has measured as bad. The milestone that matters is **30 closed
trades at positive expectancy** — that is what gates the option sleeve now,
and it is the only number that tells you whether any of this works.

If you later want more capital deployed, the defensible trigger is the same
one: a measured positive edge over a meaningful sample, not a round number.
