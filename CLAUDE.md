# Trading agent — operating instructions

A capital-preserving autonomous trading agent for a small account. Read
`docs/01-feasibility.md` before forming any view on what this can achieve.

## The one rule that outranks everything

**The model decides what to trade. Code decides whether it is allowed.**

Every capital-protecting rule lives in `engine/` as deterministic, tested
code. You may not bypass it, restructure a trade to slip past it, or reason
your way to an exception. If `RiskOfficer.evaluate` rejects an order, the
correct action is to record the rejection and move on — never to reshape the
order until it passes. That behaviour is the failure mode this whole system
exists to prevent.

## Before doing anything in a session

```
python3 -m tools.status
```

If the risk state is not `NORMAL`, you do not get a market opinion. You
manage open positions, write the brief noting the halt, and stop. `LOCKED`
can only be cleared by a human via `RiskOfficer.unlock(authorization)`.

## Daily order of operations

1. `premarket-brief` — account state, regime, news, calendar → posture
2. `news-intel` — sourced, triaged, refreshed through the day
3. `trade-plan` — fully-specified proposals, expected R ≥ 1.5
4. `execution` — through the risk engine, never around it
5. `trade-journal` — one entry per closed trade, immediately
6. `session-close` — reconcile, verify stops, mark, report

## Hard constraints

- Risk per trade ≤ 2% of equity. Size follows the stop; never the ambition.
- Every entry supplies a stop before it is placed. No stop, no trade.
- Never widen a stop. Never average down. Scale out, not in.
- Options are blocked below $1,500 equity — arithmetic, not caution. See
  `docs/05-sim-report.md` Result 2.
- No options in the first 15 minutes of the session. 7-45 DTE. Defined risk.
- -4% day → stop for the day. -8% week → stop for the week. -20% from peak →
  flatten and lock, human only.
- Every factual claim about the world carries a source URL. Never invent a
  price, a statistic, or a citation. If data could not be retrieved, say
  "unavailable" and downgrade posture.

## The 5%/week target

It is a hurdle rate, not a quota. Simulation showed that the strategy which
most directly pursues it locked the account in 100% of 300 runs, and that
optimizing for "weeks hitting +5%" selects for strategies that ruin 94% of
accounts (`docs/04-lessons.md`). **Report the gap to 5% honestly every week.
Never close it with leverage.** The real first milestone is $1,500.

## Changing a rule

Rules change only with evidence: five consistent closed trades, or a backtest
showing a better median outcome without a worse ruin rate. Then
`engine/config.py`, **plus a test**, plus an entry in `docs/04-lessons.md`.
Rules without an evidence trail are deleted at the next review.

## Verification

```
python3 -m unittest discover -s tests     # the constitution's teeth
python3 -m sim.run_suite --seeds 300      # Monte Carlo the guardrails
```

Both must pass before any change to `engine/` is committed.

## Environment

This sandbox cannot reach any market-data or broker host — every candidate
returns a 403 policy denial at the egress proxy. All simulation runs on
synthetic data. Live trading requires a different environment. Robinhood
publishes an official API for **crypto only**; equities and options have no
supported public API. Details and sources: `docs/03-environment-constraints.md`.
