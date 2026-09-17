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

**Wednesday 2026-09-16 traded nothing.** The 09:45 firing came up in an empty
container — a Routine created through `create_trigger` carries no git source —
and the salvaged session was dry-run only. Read
`docs/10-runtime-requirements.md` before touching the schedule, and
`state/rehearsals/2026-09-16.md` for what that rehearsal found: three controls
that were not controls, now fixed and tested.

**Thursday 2026-09-17 is the first session that will ever submit a live order.**
The originally-planned Thursday review was scrapped in favour of trading it.
Friday is armed with the same shape; a human reviews between them.

| When (ET) | Thu 09-17 | Fri 09-18 |
|---|---|---|
| 09:45 | preflight, open, brief, news, plan, dry run, **submit** | same |
| 12:30 | manage — trail, scale out, exit broken theses. No new entries. | same |
| 15:30 | manage + explicit carry-or-flatten per position | + **weekend** carry decision |
| 16:05 | close, journal, plain-language summary for a human | + `trading_day week` |

Each day has its **own** runner session with the repository attached
(`create_session(source_url=…, outcome_branch=…)`, then triggers bound with
`persistent_session_id`). One runner per trading day, never one spanning a
week — context accumulates within a session, and each day's judgement should
come from the committed record rather than from yesterday's conversation.

Verified end to end on 2026-09-16: trigger delivery into a repo-attached
session succeeds, and the source and state survive a container re-provision.

### Where the outcomes are

Every session commits and pushes before it ends, so **the repository is the
record** — `state/briefs/`, `state/news/`, `state/plans/`, `state/reports/`,
`state/rehearsals/`, `state/ledger.json`, `state/fills.jsonl`. The close
session also writes `state/reports/<date>-summary.md` in plain language for
someone who has not been watching.

Two limits of this shape, both deliberate:

- **No push or email notifications.** The server rejects `notifications` on a
  `persistent_session_id` Routine; only fresh-session-per-fire Routines accept
  them, and those cannot carry a repo. Rebuilding the Routines in the claude.ai
  Routines UI gets fresh sessions, notifications, *and* the connectors Phase 3
  needs — it remains the better long-term home.
- **A failed session is silent.** Nothing pushed means nothing ran. Check the
  broker directly before assuming a quiet day was an uneventful one.

## The universe, and why two sessions found nothing

`tools/screen.py` builds the tradeable universe from named criteria, commits it
to `data/universe.json`, screens it, and measures the base rate.

```
python3 -m tools.screen --build-universe   # refresh data/universe.json
python3 -m tools.screen                    # today's breakouts
python3 -m tools.screen --base-rate 90     # how often does this fire at all?
```

**Run the screen before forming a view on whether there is a setup.** The two
empty sessions of 2026-09-16/17 were not a quiet tape. The runner's candidate
list was six hardcoded tickers, and the 85-name screen quoted in those briefs
was reproducible from nothing. Measured properly: 522 of 11,833 active US
equities pass $3-$75 and the liquidity floor, 59 of the last 60 sessions had at
least one 20-day breakout, and the day a brief reported none had six.

The criteria are decisions, so they are named in `CRITERIA` and each carries
its reason. The two that bind hardest:

- **`max_price` 75.** Not a market fact — at $300 with whole-share sizing the
  engine cannot buy one share of anything dearer. `tools/smoke_submit.py`
  settled whether fractional sizing could lift it: **it cannot.** Alpaca
  rejects a fractional bracket (`fractional orders must be simple orders`), so
  a fractional entry is an entry with no attached stop. The ceiling stays.
- **`min_dollar_volume` is in IEX units, not consolidated.** The free feed
  reports IEX prints only — about 4% of tape, measured. A "$25M" floor here
  demands roughly $600M of real volume and passed 14 names out of 11,833.

## The order path is proven

`python3 -m tools.smoke_submit` places one bracket order priced where it cannot
fill, confirms Alpaca attached the protective legs, and cancels it. It refuses
unless the market is open and the account is flat, and writes nothing to the
ledger or the fill log. Verified 2026-09-17: bracket accepted, two legs, stop
attached atomically. Re-run before Phase 3 against Robinhood.

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
