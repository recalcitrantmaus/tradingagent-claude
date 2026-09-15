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
python3 -m tools.preflight_phase2    # network, keys, model, tests, state, data
python3 -m tools.status              # account detail
```

`preflight_phase2` exiting non-zero means do not trade. Note that environment
variables are snapshotted at session start: a variable added to the
environment after this session began is invisible to it, and only a new
session picks it up. The network policy is different — that applies live.

If the risk state is not `NORMAL`, you do not get a market opinion. You
manage open positions, write the brief noting the halt, and stop. `LOCKED`
can only be cleared by a human via `RiskOfficer.unlock(authorization)`.

## Daily order of operations

Bracket the day with the mechanical spine; the skills go in between.

```
python3 -m tools.trading_day open     # reconcile, mark, halt check — non-zero means DO NOT TRADE
...the six skills below...
python3 -m tools.trading_day close    # report, overnight risk, escalations
```


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
- Options are locked twice over: below $1,500 equity (you cannot size one
  contract inside the risk budget) **and** until the account shows 30+ closed
  trades at >= +0.10R measured expectancy. Simulation found long-premium
  buying negative at every capital level tested — see `docs/05-sim-report.md`
  Results 7 and 8. Affording a trade is not a reason to take it.
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

## Model routing (binding)

You cannot choose your own model — the Routine that launched this session
did. Check before durable work:

```
python3 -m tools.model_check <task>     # exit 1 means do not proceed
```

| Task | Floor | On a downgrade |
|---|---|---|
| news-intel, execution, session-close, trade-journal | Sonnet @ xhigh | warn, continue, note it in the journal |
| premarket-brief, trade-plan | Sonnet @ xhigh | warn, continue |
| weekly-review, rule-promotion, post-halt-review | **Opus @ xhigh** | **stop** |
| unlock-authorization | **Opus @ max** | **stop** |

The asymmetry is the point: a bad execution turn costs one trade; a bad rule
promoted into a SKILL.md costs every trade until someone notices. If a
blocking task cannot run, say so and leave it for a session that can.

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

**Network access was opened on 2026-09-15.** Alpaca, `agent.robinhood.com`,
the primary sources (SEC, Fed, BLS, BEA, Treasury, FINRA), CoinGecko, Yahoo
and the news outlets are all reachable. Confirm at the start of any session
that touches live data:

```
python3 -m tools.netcheck
```

Two standing cautions about data:

- **Reachable is not usable.** `stooq.com` answers HTTP 200 with a JavaScript
  bot challenge instead of data. netcheck reports that as DEGRADED. Treat any
  DEGRADED source as unavailable and say so in the brief.
- **Never trade on a single unverified price.** Every stop and every size is
  computed from it. `adapters.marketdata.cross_check()` compares the broker's
  price against an independent one; if they disagree by more than 50bps,
  **stand down on that symbol** — do not average the two or pick a winner.

Data sources, in order of precedence: Alpaca (needs keys), then
`adapters/marketdata.py` (Yahoo for equities, CoinGecko for crypto — keyless,
undocumented, fine as a cross-check, never the sole basis for a trade).

Robinhood supports agentic trading over MCP
(`https://agent.robinhood.com/mcp/trading`, long equities, options and crypto,
dedicated pre-funded account). Alpaca is the recommended paper substrate.
Setup, controls and Phase 2 exit criteria: `docs/07-deployment.md`.
