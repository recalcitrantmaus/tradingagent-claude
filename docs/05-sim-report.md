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
