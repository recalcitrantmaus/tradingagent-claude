# Handoff — read this first in a new session

**The repository is the thread.** Every decision, every piece of evidence and
every rule is committed here, and a new cloud session clones it and reads
`CLAUDE.md` automatically. You do not need the old conversation to continue;
you need this file and the docs it points at.

Last updated: 2026-09-15, end of the Phase 2 preflight session.

## Where we are

| | |
|---|---|
| Phase | **2 preflight complete. Day 1 is Wed 2026-09-16, attended.** |
| Account | $300 paper, **verified against the broker**. Never traded. Risk state `NORMAL`. |
| Network | **Open.** Custom allowlist applied and verified. |
| Broker | **Alpaca paper keys verified.** `/v2/account` returns equity $300.00, cash $300.00. |
| Tests | 49 passing |
| Live orders | **None, ever.** Nothing has touched a real or paper broker yet. |
| Routines | **None created.** Deliberate — see "How day 1 runs" below. |

## First three commands in a new session

```bash
python3 -m tools.preflight_phase2      # network, keys, model, tests, state, data
python3 -m tools.trading_day open      # reconcile, mark, halt check
python3 -m tools.model_check           # what this session is cleared to do
```

If `preflight_phase2` exits non-zero, fix what it names before anything else.

## What the preflight session settled

All of this was verified on 2026-09-15 after the close. It is evidence, not
assumption — re-run anything you doubt.

1. **The Alpaca paper keys work.** This was the top open question at the end of
   Phase 1 and it is now closed. `ALPACA_API_KEY_ID` and
   `ALPACA_API_SECRET_KEY` are both present and authenticate against
   `paper-api.alpaca.markets`. The account reads $300.00 equity, matching the
   deliberate reset — Alpaca's $100k default would have invalidated every
   sizing decision Phase 2 is meant to measure.
2. **The risk gates fire correctly at $300.** Synthetic proposals were pushed
   through `RiskOfficer.evaluate` read-only:

   | Case | Result |
   |---|---|
   | Equity, 5% stop | approved, 6 shares, risking $3.60 = 1.20% of equity |
   | No stop supplied | rejected — "every entry must define its exit" |
   | Stop above entry | rejected — "stop is not below entry" |
   | Option, 30 DTE, defined risk | rejected — below the $1,500 option floor |
   | SPY at $757.44 | rejected — size rounds to zero |

3. **SPY is untradeable at $300, and so is anything like it.** One share costs
   more than twice the account. The tradeable universe at this capital level is
   low-priced names, which is a real constraint on what the trade-plan skill
   can propose — not a bug to route around.
4. **The pipeline runs end to end.** `tools.paper_session --dry-run` reconciled
   against the broker and returned no proposals. An empty plan is a valid
   outcome and should not be treated as a failure to find something.
5. **The model-routing env var did not match the model the session actually
   ran.** `model_check` reports whatever `TRADING_AGENT_MODEL` says, and
   nothing in the environment lets a script verify that claim independently —
   `current_model()` reads only that variable or `ANTHROPIC_MODEL`. Effort is
   verifiable (`CLAUDE_EFFORT` exists and agreed); model is not. The variable
   is left as-is because it is correct for the daily-loop Routine specified in
   `docs/07-deployment.md`. **Do not trust `model_check`'s model line in an
   ad-hoc session** — confirm the session's real model out of band and record
   that in the journal. This failed safe here (it under-claimed, blocking
   Opus-tier tasks rather than permitting them), but a binding control that
   cannot verify its own input is the weakest link in the routing policy.

## How the first week runs

**Autonomous, with a human review between the two trading days.** recalcitrantmaus is in
Seattle — the open is 06:30 local — so the days run unattended and the
judgement happens after.

| When (ET) | Routine | What it does |
|---|---|---|
| Wed 09:45 | trading session | preflight, open, brief, news, plan, dry run, submit |
| Wed 12:30 | midday management | trail, scale out, exit broken theses. **No new entries.** |
| Wed 15:30 | pre-close management | final pass + explicit carry-or-flatten per position |
| Wed 16:05 | session close | reconcile, verify stops, journal, report, push |
| Thu | **attended review** | Opus tier. Read Wednesday, promote rules. Not a trading day. |
| Fri 09:45 | trading session | as Wednesday, carrying Thursday's changes |
| Fri 12:30 | midday management | as Wednesday |
| Fri 15:30 | pre-close management | **weekend** carry decision — two dark days plus a Monday open |
| Fri 16:05 | session + week close | `trading_day week`, exit-criteria checklist, push |

Four firings per trading day, not one. Two reasons, both discovered rather
than designed:

1. **A session that starts at 09:45 is not alive at 16:00**, so
   `docs/07-deployment.md`'s single 08:30 Routine that trades and closes in one
   session cannot work as written.
2. **Trailing and scale-outs exist only in `engine/sim.py`.** There is no live
   code path for them — `.claude/skills/execution/SKILL.md` describes them as
   agent actions, so they happen only while a session is running. Between
   firings the broker holds the bracket (entry, stop, target) and nothing else
   moves. Without the midday and pre-close firings, the live strategy would be
   enter-and-leave-it while the simulated returns assume a 50% scale-out at the
   first target and a 1.5 ATR trail after +1R. **The sim measures a strategy
   the live path did not implement.**

09:45 rather than 08:30 is deliberate: it puts order submission inside regular
hours rather than testing Alpaca's premarket queue unattended on the first day
that ever placed an order, and it is 15 minutes after the open, matching this
system's own view that the first 15 minutes are not to be trusted.

Each session commits and pushes `state/` before it ends. If a session does not
push, the next one starts blind.

## Model routing in practice

`model_check` reads `TRADING_AGENT_MODEL` and cannot verify it. One
environment means one value, so it cannot be simultaneously truthful for a
Sonnet trading day and an Opus review day. Resolved as follows:

- **The variable stays `claude-sonnet-5`**, truthful for the unattended
  trading days. That is where the gate matters most, because nobody is
  watching, and an over-claiming gate would green-light rule promotion on a
  session not cleared for it.
- **Thursday is attended and runs Opus.** A human confirms the real model, then
  passes it explicitly: `python3 -m tools.model_check weekly-review --model
  claude-opus-5 --effort xhigh`. The `--model` flag is a documented feature of
  the tool, and an override supplied by a present human who has verified the
  value is honest. **Never use it to assert a model you have not confirmed**,
  and never in an unattended session.

Measured floors, for reference — the trading tasks are non-blocking, so a
downgrade warns and continues rather than stopping:

| Config | Trading tasks | weekly-review |
|---|---|---|
| Opus @ high | warns: effort below the xhigh floor | blocked |
| Opus @ xhigh | clean | clean |
| Sonnet @ xhigh | clean | blocked, correctly |
| Sonnet @ max | clean | blocked, correctly |

Opus at a reduced effort level is the worst of the four: it trips the effort
floor on the trading tasks it is meant to serve, and costs more than Sonnet to
do it.

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
   `python3 -m tools.model_check <task>`. See finding 5 above for its limit.
6. **Reachable is not usable.** `stooq.com` answers 200 with a bot challenge.
   netcheck reports DEGRADED for that case.
7. **Environment variables are snapshotted at session start.** The network
   policy applies live; variables do not. Adding keys or changing
   `TRADING_AGENT_MODEL` always needs a **new session**.

## The next thing to do

Phase 2 day 1, attended, Wednesday at the open — then the rest of the week.
Runbook: `docs/09-phase2-runbook.md`. Exit criteria are in there and in
`docs/07-deployment.md` — 30+ closed trades, positive expectancy, zero
guardrail breaches, costs below gains. **Hitting +5% in a week is not one of
them.**

## Open questions carried forward

- The Alpaca paper secret key was shown in a screenshot during the build
  session, so it exists in that conversation's history. The keys were reset on
  2026-09-15, which retires that specific exposure — but the habit is the
  point: **never let a live key near a screenshot.**
- `model_check` cannot independently verify the model it reports (finding 5).
  Options considered and not yet taken: cross-check effort against
  `CLAUDE_EFFORT`, and record the session's true model in the journal rather
  than the tool's claim. Either would touch `engine/`, so it needs a test and a
  `docs/04-lessons.md` entry first.
- The two Routines in `docs/07-deployment.md` assume a per-Routine environment.
  There is one environment, so a sonnet daily loop and an Opus-tier weekly
  review cannot both hold a truthful `TRADING_AGENT_MODEL` in it. Resolve
  before the weekly review runs unattended.
- Robinhood's MCP tool surface has not been inspected — only read about.
  Verify in the app before Phase 3 (`docs/03-environment-constraints.md`).
- Whether Alpaca's two-header auth fits the Pro/Max API-credential form is
  unresolved. Matters only for live keys. `docs/08-network-policy.md`.
- Nothing has measured whether *model-generated* theses have positive
  expectancy. That is the whole question, and Phase 2 is the first data on it.
