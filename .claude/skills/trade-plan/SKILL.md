---
name: trade-plan
description: Turn a pre-market brief into concrete, fully-specified trade proposals with entry, stop, target, size rationale and invalidation. Use after the premarket-brief skill and before any order is placed, for stocks, ETFs, options or crypto. Trigger on "what should I trade", "build the plan", "propose trades", or any move from analysis to action.
---

# Trade plan

Converts a thesis into a proposal the risk engine can accept or reject. The
engine sizes the trade; this skill decides whether the trade deserves to
exist at all.

## Preconditions

- A brief exists for today and its `Posture` is not `NO_TRADE`.
- Risk state is `NORMAL`.
- If either fails, output an empty plan with the reason. An empty plan is a
  successful outcome, not a failure.

## Every proposal must specify

| Field | Rule |
|---|---|
| Instrument | Exact ticker; for options the full contract (underlying, expiry, strike, right) |
| Direction | Long only for options (defined risk). No naked short premium, ever. |
| Entry | A price and a *condition*, never "at market because I like it" |
| Stop | Mandatory. Structural (below the level that invalidates the thesis), then capped by policy |
| Target | Where you scale out, and why that level |
| Invalidation | The fact that would make you wrong, stated before entry |
| Catalyst window | What makes this move, and by when |
| Counter-case | Who is on the other side and their best argument |
| Expected R | Target distance / stop distance; **must be ≥ 1.5** or the trade is not proposed |

A proposal missing any field is not a proposal.

## Stop placement

Place the stop where the thesis dies, not where the loss is comfortable. Then
let `engine.risk.RiskOfficer.mandatory_stop` cap it. If the structural stop is
wider than policy allows, **the trade is too big for this account** — do not
tighten the stop to force a fit. Tightening a stop to afford a position is the
single most reliable way to lose money slowly.

## Asset-class notes

**Stocks / ETFs.** The core vehicle at this account size. Prefer liquid names
under $100 so position sizing has resolution — a $6 risk budget cannot
express itself in a $600 share.

**Options.** Locked by two independent gates. First, the equity floor in
`engine/config.py` ($1,500): one contract's policy-capped loss exceeds the
whole risk budget at $300, which is arithmetic, not caution. Second, and more
important, a **measured edge** — 30+ closed trades at >= +0.10R in this
account. Simulation found long-premium buying negative at every capital level
from $1,500 to $10,000 and under every stop setting tested, so affording a
contract is not a reason to buy one (`docs/05-sim-report.md` Results 7-8).
Only long OTM calls were tested; debit spreads are untested, and proposing
one requires saying so explicitly. When unlocked:
7-45 DTE, defined risk only, never in the first 15 minutes of the session,
sized in whole contracts, and only when the underlying thesis would justify
a stock trade anyway. An option is leverage on a view you already hold, not
a substitute for having one.

**Crypto.** Trades 24/7, which means the stop must be an actual resting order
or the position is unmanaged overnight. Majors only (BTC, ETH) unless the
thesis cites a primary source and survives the news-intel triage. Capped at
20% of equity in aggregate. The 35bps modelled spread is real money at this
size — crypto round-trips need a wider target to clear costs.

## Costs are a filter, not a footnote

Before proposing, compute the round-trip cost as a fraction of the expected
move. At $300, a trade whose edge is smaller than its friction is a donation.
Reject anything where modelled costs exceed 20% of the expected gain.

## Laddering

Scale *out*, not in, at this account size. Averaging down turns a bounded
loss into an unbounded one and is prohibited: a stopped-out position is
closed, and re-entry requires a new proposal with a new thesis. Scale-out is
half at the first target, stop to breakeven on the remainder, then trail.

## Output

Write `state/plans/YYYY-MM-DD.md` and a machine-readable
`state/plans/YYYY-MM-DD.json` array of proposals matching
`engine.risk.OrderProposal`. The execution skill reads the JSON; the markdown
is for the human and for the journal.
