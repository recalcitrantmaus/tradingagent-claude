# Phase 2 runbook — one week of autonomous paper trading

The goal of Phase 2 is **not** to make money. It is to produce 30+ honest
closed trades so that expectancy can be measured, and to find out whether the
guardrails hold when a real broker and real prices are involved.

A week that loses a little money with clean process is a success. A week that
makes 6% with an unstopped position is a failure.

## Before the week starts

- [ ] Alpaca paper keys in the environment; `preflight_phase2` all green
- [ ] `TRADING_AGENT_MODEL` / `TRADING_AGENT_EFFORT` set
- [ ] Paper account funded to **$300** (Alpaca defaults to $100k — reset it in
      the dashboard, or the position sizing being tested is not the position
      sizing that will run live)
- [ ] `state/ledger.json` shows `starting_equity: 300`, risk state `NORMAL`
- [ ] Two Routines created per `docs/07-deployment.md`

## Each trading day

```bash
python3 -m tools.preflight_phase2       # 1. ready?
python3 -m tools.trading_day open       # 2. reconcile, mark, halt check
```

`trading_day open` exiting non-zero means **do not trade** — it is either a
halt or a reconciliation failure, and both are stop-everything events.

Then the skills, in order:

3. `premarket-brief` — account state, regime, news, calendar → posture
4. `news-intel` — sourced and triaged; every claim carries a URL
5. `trade-plan` — full proposals, expected R >= 1.5, or an empty plan
6. `execution` — through the risk engine; `--dry-run` for day 1
7. `trade-journal` — one entry per closed trade, immediately

```bash
python3 -m tools.trading_day close      # 8. report, overnight risk, escalations
```

**Day 1 runs `--dry-run`.** Read every ticket it would have sent and satisfy
yourself the sizing and stops are what you expect. Only then start submitting.

## Each Friday

```bash
python3 -m tools.trading_day week
```

Prints the week's P&L, the honest gap to +5%, win rate, costs, expectancy, and
the Phase 2 exit criteria as a checklist. Then run the weekly review in the
`trade-journal` skill — **Opus tier, blocking**, so it belongs in its own
session or Routine.

## What to watch for

| Signal | What it means | Action |
|---|---|---|
| Costs > gains | Trading too often. The most likely quiet failure at $300. | Cut frequency, raise the minimum expected R |
| Expectancy negative over 20 trades | The edge is not there | Half size until 10 consecutive trades recover it |
| Expectancy negative over 40 trades | The strategy does not work | **Stop.** Escalate. No amount of sizing fixes negative expectancy |
| Any unprotected position | The most dangerous state in the system | Flatten or fix before anything else |
| Reconciliation failure | The ledger and the broker disagree | Stop trading until resolved by hand |
| A winning trade taken off-plan | Got paid for a mistake — teaches the wrong lesson | Flag loudly in the journal |

## Exit criteria

- [ ] 30+ closed trades
- [ ] Positive measured expectancy
- [ ] Zero guardrail breaches — no unstopped position, no order around the
      gate, no unreconciled session
- [ ] Costs below realized gains
- [ ] Every thesis traceable to a source URL
- [ ] The same model configuration intended for live

Not on the list, deliberately: **hitting 5% in any week.**

## If the account locks

`LOCKED` is -20% from peak. The agent flattens and cannot clear it. A human
runs `RiskOfficer.unlock("<note>")` with a real note. Before unlocking, run
the post-halt review — **Opus tier, blocking** — and answer: what was the
common factor, was it process or variance, and what rule changes?

A lock during Phase 2 is a finding, not a disaster. That is what Phase 2 is
for. A lock during Phase 3 is real money.
