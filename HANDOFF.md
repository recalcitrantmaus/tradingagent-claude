# Handoff — read this first in a new session

**The repository is the thread.** Every decision, every piece of evidence and
every rule is committed here, and a new cloud session clones it and reads
`CLAUDE.md` automatically. You do not need the old conversation to continue;
you need this file and the docs it points at.

Last updated: 2026-09-15, end of the Phase 1 build session.

## Where we are

| | |
|---|---|
| Phase | **1 complete. Phase 2 not yet started.** |
| Account | $300, paper, never traded. Risk state `NORMAL`. |
| Network | **Open.** Custom allowlist applied and verified. |
| Broker | Alpaca paper keys added to the environment. Untested — the session that added them could not see them. |
| Tests | 49 passing |
| Live orders | **None, ever.** Nothing has touched a real or paper broker yet. |

## First three commands in a new session

```bash
python3 -m tools.preflight_phase2      # network, keys, model, tests, state, data
python3 -m tools.trading_day open      # reconcile, mark, halt check
python3 -m tools.model_check           # what this session is cleared to do
```

If `preflight_phase2` exits non-zero, fix what it names before anything else.

## What was decided, and why (the short version)

The long version is in `docs/`. These are the conclusions that would be
expensive to re-derive or to accidentally reverse:

1. **The 5%/week target is a hurdle rate, not a quota.** It compounds to
   +1,164% annualized. The strategy that pursued it most directly hit the
   drawdown lock in 100% of 300 simulated years. `docs/01-feasibility.md`.
2. **Never optimize for "weeks hitting +5%."** In the ablation, the strategy
   that hit the target most often (13.3% of weeks) also ruined 94% of
   accounts. The KPI is compounded growth subject to survival.
   `docs/04-lessons.md`.
3. **The deposit stays at $300.** A sweep from $300 to $10,000 found returns
   flat to declining in capital. `docs/05-sim-report.md` Result 6.
4. **Options are locked twice** — below $1,500 equity and until 30+ closed
   trades at >= +0.10R. Long-premium buying lost money at every capital level
   and every stop setting tested. Only long OTM calls were tested; debit
   spreads are untested. Results 7-8.
5. **Model routing is binding.** Rule promotion, weekly review, post-halt
   review and unlock authorization require Opus tier and **block** below it.
   `python3 -m tools.model_check <task>`.
6. **Reachable is not usable.** `stooq.com` answers 200 with a bot challenge.
   netcheck reports DEGRADED for that case.
7. **Environment variables are snapshotted at session start.** The network
   policy applies live; variables do not. Adding keys or changing
   `TRADING_AGENT_MODEL` always needs a **new session**.

## The next thing to do

Phase 2: one week of autonomous paper trading on Alpaca. Runbook:
`docs/09-phase2-runbook.md`. Exit criteria are in there and in
`docs/07-deployment.md` — 30+ closed trades, positive expectancy, zero
guardrail breaches, costs below gains. **Hitting +5% in a week is not one of
them.**

## Open questions carried forward

- Alpaca paper keys are untested against the API. First `preflight_phase2` in
  a session that can see them settles it.
- The Alpaca paper secret key was shown in a screenshot during the build
  session, so it exists in that conversation's history. It is a paper key, so
  the exposure is low-consequence, but **rotate it before Phase 3** and never
  let a live key near a screenshot.
- Robinhood's MCP tool surface has not been inspected — only read about.
  Verify in the app before Phase 3 (`docs/03-environment-constraints.md`).
- Whether Alpaca's two-header auth fits the Pro/Max API-credential form is
  unresolved. Matters only for live keys. `docs/08-network-policy.md`.
- Nothing has measured whether *model-generated* theses have positive
  expectancy. That is the whole question, and Phase 2 is the first data on it.
