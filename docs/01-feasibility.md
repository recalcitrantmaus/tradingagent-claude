# Feasibility: what a $300 account can and cannot do

This document exists so the agent never has to re-argue its own mandate from
scratch, and so the human can see the arithmetic rather than a reassurance.

## The stated target

> On average, produce a profit of 5% per week.

Compounded (`engine/feasibility.target_reality_check`):

| Horizon | $300 becomes |
|---|---|
| 4 weeks | $364.65 |
| 26 weeks | $1,066.70 |
| 52 weeks | $3,792.84 |
| 3 years | $606,250.22 |

That is **+1,164% annualized**. For scale, the best long-run discretionary
track records in the industry are roughly 20-40% annualized; Renaissance's
Medallion fund, the most extreme documented case, is reported around 66%
gross annualized — and it closed to outside money precisely because the
strategy could not absorb more capital. A 1,164% annual return sustained is
not a stretch goal, it is outside the observed distribution of results.

**This is not a reason to refuse the mandate.** It is a reason to be precise
about what the target is *for*. Treated as a hurdle rate it is harmless;
treated as a quota it is fatal, because the only way to manufacture 5% in a
flat week is to raise risk until variance supplies what edge cannot.

## Why the target destroys the account rather than missing it

Feasibility reduces to one number nobody has measured yet: **expected R per
trade**. `engine.feasibility.edge_sensitivity` sweeps it:

| Win rate | Reward:risk | Edge (R/trade) | Kelly | Risk/trade needed for 5%/wk | Within Kelly? |
|---|---|---|---|---|---|
| 35% | 1.0 | -0.300 | 0.000 | impossible | no |
| 40% | 1.0 | -0.200 | 0.000 | impossible | no |
| 40% | 1.5 | 0.000 | 0.000 | impossible | no |
| 45% | 1.5 | +0.125 | 0.083 | 8.0% | yes |
| 45% | 2.0 | +0.350 | 0.175 | 2.9% | yes |
| 50% | 2.0 | +0.500 | 0.250 | 2.0% | yes |

Read the top half, not the bottom. A 45% win rate at 2:1 is a **+0.35R
expectancy**, which would be a world-class systematic edge; the table says
the target is reachable *there*. The honest question is whether this agent
has that edge, and the answer on day one is: **unknown, and the prior is
zero or negative after costs.** Every row with edge ≤ 0 says the same thing —
no amount of sizing reaches the target, and larger sizing only accelerates
the loss.

One result from the same simulation is worth internalizing. At a 45%/2R
edge with 5 trades a week, the fraction of weeks finishing at +5% or better
is **40.7% — and it is identical at 2%, 5% and 20% risk per trade.** Whether
a week clears the target depends on how many trades win, not on how big they
are. Sizing up does not buy more winning weeks. It only changes how much the
other 59% of weeks cost. At 20% risk per trade, 8.7% of one-year paths go to
**zero**.

## The structural constraints of $300

1. **Options are arithmetically unaffordable.** A 2% risk budget on $300 is
   **$6**. One option contract at a $2.00 premium with the policy 40% stop
   risks **$80**. For a single contract to fit the budget, equity must exceed
   `2000 x premium` — roughly **$1,500** for the cheapest liquid contracts.
   This is why `RiskConfig.option_min_equity = 1500`. The agent is not being
   timid about options; it cannot buy one without breaking the rule that
   keeps it alive.
2. **Resolution.** A $6 risk budget with an 8% stop buys about $75 of stock.
   In a $580 ETF that is zero shares. The universe must skew to liquid names
   under ~$100, or use fractional shares where the broker supports them.
3. **Costs dominate.** Spread and slippage are proportional, so they do not
   shrink with the account — but the edge needed to clear them is measured
   against a much smaller base. This is why `trade-plan` rejects any setup
   whose modelled friction exceeds 20% of the expected gain.
4. **Settlement.** On a cash-account model, proceeds are unavailable until
   T+1, so the account cannot recycle capital as fast as the target assumes.

## What the mandate becomes

The user's conditions are, in priority order:

1. *"continued or extravagant losses are not to be permitted under any
   circumstances"* — a hard constraint.
2. *"grow that over time so that it has more to use in investments"* — the
   objective.
3. *"5% per week on average"* — the aspiration.

When (3) conflicts with (1), (1) wins, every time, mechanically, in
`engine/risk.py` rather than in the agent's judgment. The operational
objective is therefore: **maximize compounded growth subject to never
breaching the drawdown lock**, and report the gap to 5% honestly every week
rather than closing it with leverage.

The first milestone is not 5% a week. It is **$1,500** — the point at which
the instrument set actually opens up.

## Sources

- [FINRA — Frequent Intraday Trading: Understanding the Basics](https://www.finra.org/investors/investing/investment-products/stocks/day-trading)
- [SEC — Margin Rules for Day Trading (PDF)](https://www.sec.gov/files/daytrading.pdf)
- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
