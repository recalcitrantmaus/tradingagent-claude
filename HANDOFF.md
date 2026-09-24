# Handoff — read this first in a new session

**The repository is the thread.** Every decision, every piece of evidence and
every rule is committed here, and a new cloud session clones it and reads
`CLAUDE.md` automatically. You do not need the old conversation to continue;
you need this file and the docs it points at.

Last updated: **2026-09-24**, end of the Thursday build session.
Develop on `claude/trading-agent-robinhood-cb9xo7`.

## Where we are

| | |
|---|---|
| Phase | **2, week 2. Live paper trading.** |
| Account | **$299.62** paper, flat, risk state `NORMAL`. Verified against the broker 2026-09-24. |
| Closed trades | **1** — DT, −$0.37, **−0.139R**. Exit criterion is 30+ at ≥ +0.10R. |
| Tests | **423 passing**, incl. an e2e spine and one regression test per shipped defect |
| Sim | `sim.run_suite --seeds 300` → 0.0% ruin |
| Routines | **None scheduled.** Friday 2026-09-25 is unarmed. |
| Options | Locked (needs $1,500 **and** 30 closed trades at ≥ +0.10R) |

**Run this first, and believe it over this file:**

```bash
python3 -m tools.preflight_phase2    # network, keys, model, tests, state, data
python3 -m tools.status              # equity, realized P&L, expectancy, stops
python3 -m tools.trading_day open    # non-zero means DO NOT TRADE
```

## The two things a fresh session cannot work out for itself

**1. You do not know which model you are.** `TRADING_AGENT_MODEL` is an
environment default — one value for every session here — and preflight says so
out loud. For any **blocking** task (weekly-review, rule-promotion,
post-halt-review, unlock-authorization) read the real value from the session
record (`get_session` → `session_context.model` and
`external_metadata.last_served_model`) and pass it with `--model`.

**2. You may never write your own `--authorization`.** That string is the
authorising human's, in their own words, and it is appended to
`state/authorizations.jsonl` with the session id. The gate is **attributable,
not enforceable** — nothing in-process can establish that a human is present,
and the first attempt at detecting one read an environment variable and never
once bound (M-22/M-26). A trivial or previously-used string is refused, so it
cannot be baked into a Routine prompt. If nobody is there to type it, leave the
task for a session where somebody is.

## What the live week actually produced

**One fill, and it was instructive.** DT filled at $58.47 on 2026-09-23 and was
flattened at $58.10 — **−$0.37, −0.139R**. The flatten was a mistake of mine,
not a stop: I had shipped a pre-close refusal on Alpaca order status `held`,
reading it as "the stop never went live". Alpaca staff confirm the opposite —
`held` means the broker is monitoring the stop and has not routed it to an
exchange yet, which is the **normal working state** for a resting stop. DT
never traded below 57.39 that day, so holding would have been −0.075R; the
flatten cost about 0.064R. Reverted in full; five tests now pin `held` as
valid, and `ACTIVE_STATUSES` carries the staff quotes inline so nobody
re-litigates it.

The transferable part is the epistemics: I reasoned from **silence in a
reference**. `held` is absent from Alpaca's own documented status list, and I
read absence as malfunction. Silence in a reference means the reference is
incomplete. The right response to an unreadable source was to treat the
question as unresolved and **not ship a refusal on it**.

## Rules added this week (all tested, all in `engine/`)

- **Aggregate open risk ≤ 4% of equity**, measured from the current price
  across the whole book. Without it, 4 positions × 2% put 8% at risk — twice
  the daily breaker — and the breakers cannot help, because they stop *new*
  trades and cannot unwind stops already resting.
- **Size tapers across concurrent positions**: 2.00%, 1.00%, 0.50%, 0.25%
  (`correlated_risk_decay = 0.5`). This is "conservative on most, let one run"
  expressed as **size** rather than as targets — a target controls upside while
  size and the stop control loss, so trimming targets on the also-rans would
  forfeit their winners and keep their full downside. Swept at 3000 seeds:
  worst drawdown 20.9% → 17.8%, locked accounts 15/3000 → 0.
- **Diversification is not available to this book.** Measured 2026-09-22,
  60-day return correlation across the day's own signals ran **0.45–0.83**,
  including a space name and a broad-market ETF. Limit the total; do not expect
  picking different names to do it. Known side effect: whole-share rounding
  means the tapered 2nd and 3rd budgets can only afford low-volatility names
  (open as T-7).
- **Trading dates key on America/New_York**, not UTC.
- **Opus floor at the open, pre-close and close.** The risk engine protects
  against bad decisions; it cannot protect against bad *data*, and a proposal
  built on a wrong number passes every gate because size, stop and expected R
  are all computed correctly from it.

## Six years of data now sit behind the entry rule

`tools/pit_study.py --fetch` caches 2,472 symbols from 2020-07 (51 MB, the IEX
feed's start). `tools.multiyear` and `tools.multiproxy` re-run the entry and
proxy studies year by year off one cache load.

**The headline: chase beats retest, and my one-year "correction" was noise.**
2026 alone said retest won; six years say the opposite, and 2026 is the single
year that behaved differently. Quote the **year-level** t, never the pooled
one — pooling 13,912 trades pretends they are 13,912 independent draws when
trades inside one year share a market.

No signal-time feature separates the breakouts that never pull back from the
ones that do. `breakout_%` predicts the *label* strongly and the *return* not
at all, because within the no-pullback group it predicts return negatively and
the two effects cancel.

## Testing is now a binding cadence, not a habit

See **CLAUDE.md → Verification → "When to run what"**. In short: module edit →
the tests naming it; `engine/` edit → whole suite + sim; major update → whole
suite + the e2e spine; **any defect → a regression test first**; before a
commit → the suite **as its own command**, never chained into `&&` (that is how
a commit went out over a red suite on 2026-09-23).

```bash
python3 -m unittest discover -s tests -t .   # the -t . is load-bearing
```

**Without `-t .`** unittest imports test modules as top-level modules,
`tests/__init__.py` never runs, and the suite writes to the **real** `state/`
directory. A test wrote a phantom BUY into `state/fills.jsonl` that way on
2026-09-24. One test now fails loudly if the sandbox was not in force, and a
repo-wide invariant test refuses any invocation missing the flag.

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

## Sources: what works, and what the skills now point at

Rebuilt 2026-09-17 after five of six news outlets turned out to be serving bot
walls while netcheck reported them healthy. `python3 -m tools.netcheck --all`
is the current truth; every host below was verified twice — it answered, *and*
its body parsed into the data it is supposed to carry.

- **Market news:** Alpaca's `/v1beta1/news` (authenticated, timestamped,
  symbol-tagged, on a host already in the required tier). It is **Benzinga
  only**, so it is one outlet and cannot corroborate itself.
- **Macro numbers:** `adapters.fred` — jobless claims, yields, spreads, CPI,
  unemployment, VIX, keyless. Every reading carries its observation date and a
  staleness count. This is how the DOL claims print is obtained; `www.dol.gov`
  itself refuses us.
- **Filings:** `data.sec.gov` for XBRL facts as JSON, `www.sec.gov` for EDGAR.
- **News lanes:** seven RSS feeds (BBC, NPR, Guardian, Fox Business, The Hill,
  Cointelegraph, Decrypt) carrying the political spread. Use an outlet's feed
  rather than its HTML page — feeds are built for machines.
- **Dead, do not re-add without re-testing:** Reuters, AP, CNBC, MarketWatch,
  The Block, stooq (bot walls); api.census.gov (needs a key, and FRED serves
  the same series without one).

The three skills that consume sources — `news-intel`, `premarket-brief`,
`trade-plan` — were pointing at the dead outlets and at none of the new tools.
They now name the working ones explicitly. **Building a capability and wiring
it into the skill that needs it are two separate jobs**, and only the second
one changes what a session actually does.

## What is still unproven

The only question Phase 2 exists to answer is whether model-generated theses
have positive expectancy, and **one closed trade is not evidence**. Also still
unproven:

- the posture gate blocking a **real** order (only the `RISK_OFF` tightening
  path has run)
- an empty plan binding against a scanner that **disagrees**
- the management path actually managing: trailing, scaling out, an overnight
  carry with a position on
- whether the strategy or the R ≥ 1.5 threshold, rather than the plumbing, is
  what keeps the plan empty

## Open queue, carried into Friday

| | |
|---|---|
| **T-7** | the size taper biases the 2nd and 3rd slots to low-volatility names (whole-share rounding) |
| **T-10** | `recheck()` is written, tested and **parked, uncalled** — activate at a session END, never mid-day |
| **T-15** | preflight reports declared, not harness-verified, effort |
| **T-16** | Yahoo cross-check rate-limits under load; must never gate a trading day |
| **W-1..W-3** | the day-trade budget has never counted anything |
| **M-7** | short entry bypasses the risk gate |
| **M-8 / M-18 / M-9** | see `state/reviews/2026-09-23-wednesday-close-queue.md` |
| housekeeping | orphan branch `claude/wizardly-carson-5qjgn5` needs deleting — I get 403, a human must do it |

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

**Friday 2026-09-25 is unarmed — no Routines are scheduled.** Arming it is the
first decision of the next session. The agreed shape:

| When (ET) | Model | What |
|---|---|---|
| 09:45 | **Opus @ xhigh** | preflight, open, brief, news, plan, submit |
| 12:30 | Sonnet @ xhigh | manage only — trail, scale out, exit broken theses. No new entries. |
| 15:30 | **Opus @ xhigh** | pre-close: carry-or-flatten per position, overnight gap risk |
| 16:05 | **Opus @ xhigh** | close, journal, summary in plain language |

Two standing decisions about the schedule:

- **If nothing trades at the open, cancel the rest of that day except the
  close.** Until something fills, the extra firings produce no testing.
- A Routine created through `create_trigger` **carries no git source** — it
  inherits the environment, not the repo — and an unattended session cannot
  clone its way out, because the repo is private and `git clone` needs an
  approval nobody is there to give. Attach the repository at session start, or
  build the Routine in the claude.ai Routines UI with the repo attached. See
  `docs/10-runtime-requirements.md`. One-shot Routines do not appear in the UI
  even when they exist; `list_triggers` is the truth.
- A Routine's prompt can only be edited **from the session it posts into**.

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
