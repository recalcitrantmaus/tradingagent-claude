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

**`CLAUDE_EFFORT` is the exception, and it matters.** It tracks the *turn*, not
the session — measured `high` at 13:39Z and `medium` at 20:07Z inside one
session on 2026-09-22. Anything that reads it once and treats the answer as a
property of the session is wrong. See "Re-check the floor at the write" below.

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
- **Aggregate open risk ≤ 4% of equity**, measured from the current price
  across the whole book, so that if every stop filled at once the loss is
  exactly the daily halt. Without it, 4 positions × 2% put 8% at risk — twice
  the daily breaker and exactly the weekly one — and the breakers cannot help,
  because they stop *new* trades and cannot unwind stops already resting.
  This is also the only diversification control available: measured
  2026-09-22, 60-day return correlation across the day's own signals ran
  0.45–0.83 including a space name and a broad-market ETF, so a long-only
  breakout book has no uncorrelated pair to spread into. Limit the total; do
  not expect picking different names to do it.
- **Size tapers across concurrent positions**: the first gets the full 2%,
  each additional one half the previous (2.00%, 1.00%, 0.50%, 0.25%). This is
  "conservative on most, let one run" expressed as size rather than as
  targets — a target controls upside while size and the stop control loss, so
  trimming targets on the also-rans would forfeit their winners and keep their
  full downside. It needs no correlation input because there is no
  uncorrelated pair to find. Swept at 3000 seeds on two strategies: median
  +1.65, p05 +10.00, worst drawdown 20.9% → 17.8%, locked accounts 15/3000 →
  0. Note the side effect at this account size: whole-share rounding means the
  tapered 2nd and 3rd budgets can only afford low-volatility names.
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
| news-intel, execution, trade-journal | Sonnet @ xhigh | warn, continue, note it in the journal |
| **premarket-brief, trade-plan** (the open) | **Opus @ xhigh** | warn, continue |
| **pre-close, session-close** | **Opus @ xhigh** | warn, continue |
| weekly-review, rule-promotion, post-halt-review | **Opus @ xhigh** | **stop** |
| unlock-authorization | **Opus @ max** | **stop** |

The asymmetry is the point: a bad execution turn costs one trade; a bad rule
promoted into a SKILL.md costs every trade until someone notices. If a
blocking task cannot run, say so and leave it for a session that can.

**Why the open and the close carry an Opus floor** (raised 2026-09-22). The
risk engine protects against bad *decisions*; it cannot protect against bad
*data*. A proposal built on a wrong number passes every gate, because the
size, the stop and the expected R are all computed correctly from it. RKLB on
2026-09-22 would have cleared the entire engine on a 20-day high that was
0.91% too low, and the same defect had ATR wrong in 59 of 59 names. Only a
model cross-checking its own feed caught it. The open is also the only session
that *forms beliefs about the world* — the rest execute against beliefs already
formed — so the asymmetry follows the task, not the phase. Pre-close prices
overnight gap risk across a book whose names correlate 0.45–0.83, and a gap
does not respect stops. The close is where findings are promoted or lost.

**This floor is meant to be earned down.** Every data artifact a model finds
should become a deterministic check; `cross_check()` exists for prices and
belongs on levels and ATR next. Opus at the open is right while the data layer
is still surprising us, not forever.

**A blocking task needs two things, and you can supply only one of them.**
Pass `--model` after reading the real value from the session record
(`get_session`, `session_context.model` and
`external_metadata.last_served_model`) — the environment default is the same
for every session here and is routinely wrong. And pass
`--authorization "<why, in the authorising human's own words>"`, which is
appended to `state/authorizations.jsonl` with the session id and timestamp.

```
python3 -m tools.model_check rule-promotion --model claude-opus-5 \
    --authorization "recalcitrantmaus: promote the 2% cap change, evidence in docs/04"
```

**The picker is not the served effort** (E-1, 2026-09-26). The session
record and the picker can show Extra high while turns are served lower. The
gate reads the harness value, and that value wins over `--effort`. If a
check refuses on effort: close any other client attached to the session,
toggle the web picker away and back, send a new message, and re-check.

### Re-check the floor at the write (binding, T-10)

`model_check` clears a task **once, at its start.** Because `CLAUDE_EFFORT`
tracks the turn, a blocking task that cleared at xhigh can perform its durable
write several turns later at medium, with no signal at all — `session-close`
ran two notches below its floor on 2026-09-22 and only the journal caught it. A
point-in-time check on a per-turn value certifies **the turn it was taken in,
not the write.**

So for a blocking task — weekly-review, rule-promotion, post-halt-review,
unlock-authorization — run this **immediately before each durable write**: the
`engine/config.py` edit, the SKILL.md write, the `docs/04-lessons.md` entry.
Not at task start. Where a downgrade would actually cost something.

```
python3 -m tools.model_check rule-promotion --at-write --started-at xhigh
```

**Exit 1 means abandon that write.** Do not finish "just this one" — a rule
promoted below its floor is exactly the cost this priced. Say what you were
about to write, and leave it for a session that holds the floor.

This is a procedure, not an interlock, and is recorded as the weaker thing it
is: the writes it guards are made with file tools, so there is no line of code
to hook. The one blocking write that *is* a function call —
`RiskOfficer.unlock()`, which re-arms an account the breakers took offline —
re-checks the floor itself and raises `EffortFloorRefusal`. A locked account
therefore cannot be cleared below `max` effort, and the lock stays on until a
session that holds it runs the unlock.

A trivial authorization ("ok", "approved") is refused, and so is one used
before, verbatim — so it cannot be baked into a Routine prompt and fired on a
schedule. **Do not write your own authorization.** That string is a human's,
and the gate cannot tell the difference: it is *attributable*, not
enforceable. Nothing in-process can establish that a human is present — the
first attempt at this read an environment variable and never once bound (see
M-22/M-26 in `docs/04-lessons.md`). What the log does is make a false claim
permanent and signed. Leave the task for a session where someone can type it.

## Changing a rule

Rules change only with evidence: five consistent closed trades, or a backtest
showing a better median outcome without a worse ruin rate. Then
`engine/config.py`, **plus a test**, plus an entry in `docs/04-lessons.md`.
Rules without an evidence trail are deleted at the next review.

## Verification

```
python3 -m unittest discover -s tests -t . # the constitution's teeth
python3 -m sim.run_suite --seeds 300      # Monte Carlo the guardrails
```

**The `-t .` is not cosmetic.** Without it, `unittest` imports test modules as
top-level modules, `tests/__init__.py` never runs, and the suite writes to the
REAL `state/` directory. On 2026-09-24 a test wrote a phantom fill into
`state/fills.jsonl` that way. `tests/__init__.py` redirects state to a
throwaway directory, and one test fails loudly if it was not in force.

Both must pass before any change to `engine/` is committed.

### When to run what (binding)

A "script" here is a **module** — one `.py` file, addressed as `tools.status`,
`engine.risk`. There is no trigger-equivalent in the language; the thing that
fires unattended is a **Routine**, and it runs `tools/trading_day.py`.

| After | Run | Why |
|---|---|---|
| **any edit to a module** | the test files that name it (command below) | catches the edit itself, in seconds |
| **any edit under `engine/`** | the whole suite **and** `sim.run_suite` | the engine is the thing the model may not bypass; a local pass proves nothing about the gates it composes with |
| **a major update** — touches 2+ modules, changes a signature, or crosses the money/state/order path | the whole suite **and** `tests/test_e2e_trading_day.py` (inside it) | unit tests pin functions; only the e2e spine catches a contract broken *between* them. That is how the recovered-position reconciliation bug was found |
| **any defect, ever** | add a test to `tests/test_regressions.py` first, then fix | a defect without a test is a defect scheduled to return |
| **before a commit** | the whole suite, as its own command | never chain it into `&&`; the shell reports the last command's status, which is how a commit went out over a red suite on 2026-09-23 |

Which test files cover what you just changed:

```
git diff --name-only HEAD | grep '\.py$' | xargs -r -n1 basename | sed 's/\.py$//' \
  | while read m; do grep -rlw "$m" tests/ --include='*.py'; done | sort -u
```

If that prints nothing, the module you changed has **no test**. Write one
before you commit, or say plainly in the commit message that it is untested
and why.

Regression tests are not optional and not a "best practice" to be weighed.
`tests/test_regressions.py` carries one test per shipped defect, grouped by the
four shapes in `docs/04-lessons.md`: a control reading a value that cannot vary
with what it measures; a check that passes vacuously; a datum that means
something other than it appears; a control that is correct in isolation and
never receives the state that makes it bind. **When a new bug does not fit one
of the four, that is the finding** — write the shape down.

A test suite is only worth its green. Periodically re-break a fix on purpose
and confirm the suite goes red; a guard that scores zero against its own bug is
not a guard. Clear `__pycache__` when you do — a same-size edit restored inside
the same mtime second leaves CPython running the mutated bytecode, which
happened on 2026-09-24 and made a mutation look caught when it was not.

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
