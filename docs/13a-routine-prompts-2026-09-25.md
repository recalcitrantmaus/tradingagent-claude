# Routine prompts — Friday 2026-09-25

Armed on the evening of Thursday 2026-09-24 ET by an attended session
(`session_01YGq4H9eezU7hawFM3bRgE2`, the "arming session"), per HANDOFF.md
"The next thing to do". recalcitrantmaus is **not available from the open to the close**,
so every firing below is unattended and must not end on a question.

The prompts are stored here verbatim so they are versioned and recoverable;
`list_triggers` is the truth for what is actually armed. One-shot Routines do
not appear in the claude.ai Routines UI.

## Shape

Two runner sessions, each created with `create_session(source_url=…,
source_revision=…, outcome_branch=claude/trading-agent-robinhood-cb9xo7)`, so
the repository is attached at session start (docs/10) and pushes land on the
working branch. Triggers are one-shots bound with `persistent_session_id`. A
bound trigger runs on its session's model, so the Sonnet midday needs its own
session.

| ET | UTC | firing | runner (model) | trigger |
|---|---|---|---|---|
| 09:45 | 13:45 | OPEN — preflight, open, brief, news, plan, submit | Opus `session_01Xn54wA68nkt7KHDaoj53RL` (claude-opus-5-5) | `trig_016ar4ZQpTzZjZLYdJjtJvFg` |
| 12:30 | 16:30 | MIDDAY — manage only, no new entries | `session_01AvBRnTBfaiGqP8DvKpjsd1`, created as Sonnet; **switched to Opus 5.5 at Extra high by recalcitrantmaus, 2026-09-25 ~00:40 ET** | `trig_01VQMv7HMhRVUBZqym2nsAsY` |
| 15:30 | 19:30 | PRE-CLOSE — weekend carry-or-flatten, gap risk | Opus runner | `trig_01RBYdpna33fdKvNet3GoMzn` |
| 16:05 | 20:05 | CLOSE — close, journal, week, summary | Opus runner | `trig_01K8aKJt8rf2wDnVGpuoJsPU` |

**Report-back.** Every firing ends by writing its report to
`state/reports/2026-09-25-relay-FIRING.md`, pushing it, and then calling
`fire_trigger` on a poke-only relay trigger bound to the arming session
(`trig_01DcJrhKop6mfes4uutV3ChR`), with the report as the appended text. The
arming session verifies it read-only against git and the broker and replies.
The committed file is the fallback if `fire_trigger` fails.

**Watchdogs.** A failed session is silent (HANDOFF), so three one-shot
watchdogs fire into the arming session. The relay handler deletes a firing's
watchdog when its report arrives; a watchdog that fires anyway means the report
did not arrive, and it diagnoses from the session record, git and the broker.

| ET | UTC | watchdog | trigger |
|---|---|---|---|
| 11:15 | 15:15 | WD-OPEN | `trig_018YcMSF5Tn3EqiaNapu1cdf` |
| 13:45 | 17:45 | WD-MIDDAY | `trig_01FRbJ8ysXYiP4ZKw8SecQ5M` |
| 17:15 | 21:15 | WD-CLOSE (covers pre-close too) | `trig_01G9Y7qKY6KZDARvyejSM3Qw` |

**Standing rule, applied by the arming session on the OPEN report** (or by
WD-OPEN if it never arrives): if the broker shows no position and no open
order after the open, MIDDAY, PRE-CLOSE and WD-MIDDAY are deleted. CLOSE always
runs.

**Findings** from every Friday firing go in one file,
`state/reviews/2026-09-25-friday-queue.md`, as F-1, F-2, … in sequence. One
prefix for the day avoids Wednesday's T-n/W-n split.

**Rehearsal, 2026-09-24 ~23:10 ET.** Each runner got a read-only first turn:
repo, model, effort, preflight, model_check, then a post-back through the
relay. The Sonnet runner's post-back worked. Both runners read
`CLAUDE_EFFORT=high`, because `create_session` sets no effort and the CLI
default is `high`. A repo `effortLevel` setting was tried and reverted: the
runners then read `medium` (Opus) and `high` (Sonnet). See docs/10 §6. The
firings warn, continue and record the effort they read.

---

## Relay handler — fires into the arming session

<!-- ---8<--- BEGIN RELAY ---8<--- -->
RELAY — a Friday 2026-09-25 runner has finished a firing, and its report is appended below. recalcitrantmaus is not available during today's session. They read this thread afterwards, and the runner's report is their summary, so keep your own reply short.

1. The report's first line names the firing: REHEARSAL, OPEN, MIDDAY, PRE-CLOSE or CLOSE.

2. Verify it, read-only. Locate the repo (REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"), then run git fetch origin claude/trading-agent-robinhood-cb9xo7 and confirm the runner's commit is on that branch. Then check the broker:
python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash']); print('positions',a.positions()); print('orders',[(o['symbol'],o['side'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders(nested=True)]); print('UNPROTECTED:',a.positions_without_stops())"
Name any disagreement with the report.

3. Delete that firing's watchdog so it does not fire:
OPEN: WD-OPEN trig_018YcMSF5Tn3EqiaNapu1cdf
MIDDAY: WD-MIDDAY trig_01FRbJ8ysXYiP4ZKw8SecQ5M
CLOSE: WD-CLOSE trig_01G9Y7qKY6KZDARvyejSM3Qw
PRE-CLOSE and REHEARSAL have no watchdog.

4. OPEN only: apply recalcitrantmaus's standing rule. If the broker shows NO position AND NO open order, delete MIDDAY trig_01VQMv7HMhRVUBZqym2nsAsY, PRE-CLOSE trig_01RBYdpna33fdKvNet3GoMzn and WD-MIDDAY trig_01FRbJ8ysXYiP4ZKw8SecQ5M. CLOSE trig_01K8aKJt8rf2wDnVGpuoJsPU always runs. If anything filled, or an entry is resting that could still fill, keep all of them.

5. If UNPROTECTED is not empty, lead with it. Message the runner that owns the day's next firing (Opus session_01Xn54wA68nkt7KHDaoj53RL, Sonnet session_01AvBRnTBfaiGqP8DvKpjsd1) with a one-shot trigger bound to it (create_trigger with persistent_session_id set to that session and run_once_at two minutes out). Tell it to fix it or flatten it through the execution skill now, and to report back through this relay. SendMessage cannot reach cloud sessions from this session.

6. Reply in at most eight lines: which firing it was, whether it verified and any discrepancy, what you deleted, and anything that needs recalcitrantmaus.

Do not trade from this session. Do not edit engine/, do not run a blocking task, and never write an --authorization.
<!-- ---8<--- END RELAY ---8<--- -->

---

## 1. OPEN — 09:45 ET (13:45 UTC), Opus runner

<!-- ---8<--- BEGIN OPEN ---8<--- -->
Friday 2026-09-25, 09:45 ET. Session open. The market opened 15 minutes ago.

YOU ARE UNATTENDED. recalcitrantmaus is not available from the open to the close today. Nobody will answer a question, so decide within the rules, or stand down and record why. Do not end a turn waiting for input.

The rule that outranks everything: the model decides what to trade, and code decides whether it is allowed. If RiskOfficer rejects an order, record the rejection and move on. Never reshape the order until it passes.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If there is no repository, do not clone it. Report that and stop.
git pull origin claude/trading-agent-robinhood-cb9xo7
Read CLAUDE.md and HANDOFF.md from the pulled tree.
python3 -m tools.preflight_phase2    # non-zero means DO NOT TRADE
python3 -m tools.trading_day open    # non-zero means DO NOT TRADE
python3 -m tools.netcheck
python3 -m tools.status

MODEL AND EFFORT. Read your real model from the session record: get_session with session_id omitted, then session_context.model and external_metadata.last_served_model. Also run echo $CLAUDE_EFFORT. TRADING_AGENT_MODEL says claude-sonnet-5, and that is wrong for this session. This firing's floor is Opus @ xhigh:
  python3 -m tools.model_check premarket-brief --model THE_MODEL_YOU_READ
  python3 -m tools.model_check trade-plan --model THE_MODEL_YOU_READ
A downgrade warns and continues. Record it in the journal. Never pass --authorization.

Starting state per HANDOFF (believe the broker over this): $299.62, flat, NORMAL. One closed trade: DT at -0.139R.

=== 1. THE TRADING SET ===

Run premarket-brief, then news-intel, then trade-plan, then execution:
  python3 -m tools.paper_session --submit

Use the committed universe (data/universe.json) and run python3 -m tools.screen BEFORE concluding there is no setup. The plan states the denominator it screened. An empty plan is binding: trade nothing. The scanner is not consulted after an empty plan.

Carry-forward cautions. Each of these cost something this week:
 a. `held` is the NORMAL working status of a resting bracket stop at Alpaca. It is not a fault. Do not flatten, re-stop or "fix" a position because its stop reads held. positions_without_stops() is the check, and [] means protected. On Wednesday, flattening DT on this misreading cost 0.064R.
 b. The price NOW is adapter.last_trade(). Bars are SIP, completed sessions only, 15 minutes delayed. Never read bars[-1].close as the current price.
 c. Cross-check every price you would trade (adapters.marketdata.cross_check). More than 50bps of disagreement means stand down on that symbol. If Yahoo returns HTTP 429 (T-16), retry with a backoff. If it is still unavailable, that symbol's price is unverified: stand down on that symbol and record it. Never trade on a single price, and do not halt the whole day over a rate limit.
 d. Size tapers across positions at 2%, 1%, 0.5% and 0.25%, and aggregate open risk is capped at 4%. A "tapered" refusal is the rule working. Record it and move on. Never re-price, re-stop or swap in a cheaper name to make it fit. T-7's bias toward low-volatility names is known.
 e. There is no sector rule. Do not add one.
 f. Targets are mandatory, and expected R must be at least 1.5. D-24 is open, and changing that is not yours to do. If you refuse a candidate on structural R, write down the exact level and why.
 g. Do not open crypto, because no stop attaches (D-21). Options are locked.
 h. Ignore the "day trades 0 / 3" line. It reads a field that nothing writes (W-1..W-3). This is a CASH account, so the binding constraint is T+1 settled cash, and the engine gates on that.
 i. It is FRIDAY. Anything filled today faces a WEEKEND carry decision at 15:30.

Every factual claim carries a source URL. Never invent a price or a citation. If data could not be retrieved, write "unavailable" and downgrade posture. WRITE THE PLAN OUT PER NAME, including the refusals and which constraint bound each one.

=== 2. RECORD ===

Commit everything in state/. Push BY NAME:
  git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
Then confirm the commit is on origin.
New findings go in state/reviews/2026-09-25-friday-queue.md as F-1, F-2, and so on. That one file and sequence is shared by all of today's firings. Continue the sequence and never renumber anything.
Do not run the weekly review. Do not promote, change or delete any rule. Do not edit engine/. Never write an --authorization.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened, including a stop at step 0 ===

a. Write the report to state/reports/2026-09-25-relay-open.md, commit it, push it by name, and confirm it is on origin.
b. Post it. Call fire_trigger (mcp__Claude_Code_Remote__fire_trigger, loading it with ToolSearch if needed) with trigger_id trig_01DcJrhKop6mfes4uutV3ChR and text = the report.

The first line must be exactly:  OPEN 2026-09-25 — ONE_LINE_HEADLINE
Then these headings, in this order, each filled in or marked "none":
 1. What occurred: the screen denominator; proposed, approved, and refused (naming the constraint); submitted, filled (price against the plan, and slippage) and resting.
 2. What did not occur, and why. Name any of these that ran against reality for the first time: the posture gate blocking a real order; an empty plan binding against a scanner that disagrees; an engine-sized order reaching a fill.
 3. Account: equity, day P&L, cash drift (always, including zero), positions with stop status, and UNPROTECTED.
 4. Plan for the rest of the day, including whether the standing rule applies (nothing filled and nothing resting means midday and pre-close are cancelled, and the close still runs).
 5. Findings (F-n)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom (a later firing, or recalcitrantmaus)
 8. Provenance: model and effort as read, and the commit pushed
Keep it under about 60 lines. Detail belongs in the committed files. If fire_trigger fails or is refused, add that to the committed file and say so in your final reply.
<!-- ---8<--- END OPEN ---8<--- -->

---

## 2. MIDDAY — 12:30 ET (16:30 UTC), Sonnet runner

<!-- ---8<--- BEGIN MIDDAY ---8<--- -->
Friday 2026-09-25, 12:30 ET. Midday management. This firing MANAGES existing risk. It opens no new risk, for any reason.

YOU ARE UNATTENDED. recalcitrantmaus is not available until after the close. Decide within the rules, or stand down and record why. Do not end a turn waiting for input.

This firing exists only because the open left something on the book (a position, or an entry still resting). The open ran in a DIFFERENT session. The repository is the thread.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If there is no repository, do not clone it. Report that and stop.
git pull origin claude/trading-agent-robinhood-cb9xo7
Read CLAUDE.md, state/reports/2026-09-25-relay-open.md and today's plan in state/plans/2026-09-25.*
MODEL: read it from the session record (get_session, session_id omitted), and run echo $CLAUDE_EFFORT. Then:
  python3 -m tools.model_check execution --model THE_MODEL_YOU_READ
Never pass --authorization.

=== 1. RECONCILE AND CHECK PROTECTION ===

python3 -m tools.trading_day open
python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash']); print('positions',a.positions()); print('orders',[(o['symbol'],o['side'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders(nested=True)]); print('stops',a.resting_stops()); print('UNPROTECTED:',a.positions_without_stops())"

UNPROTECTED must be []. Anything listed is unmanaged risk: fix it or flatten it through the execution skill before anything else, and lead your report with it. A stop leg reading `held` is the NORMAL working state of a resting stop at Alpaca. [] with held legs means the position is protected. Do not flatten on held.

Report the cash-drift line unconditionally. A fill this morning should explain any drift. An unexplained drift alongside a fill means the fill log and the broker disagree.

=== 2. VERIFY THIS MORNING'S SUBMIT ===

 - Anything FILLED: its state/fills.jsonl row must carry the broker's filled_avg_price and filled_qty (B-15). Report slippage against the plan.
 - Anything NOT filled: fills.jsonl has no row for it, and ledger["working_orders"] carries it.
 - Every protective leg reads time_in_force gtc (B-16).

=== 3. MANAGE, under the rules as they are ===

Scale out at the first target and move that stop to breakeven. Trail the remainder past +1R by 1.5 ATR. Exit a broken thesis whatever the P&L. NEVER widen a stop, NEVER average down, NEVER add. NO NEW ENTRIES.
Observe and record, without acting: where each take-profit sits, and whether the move looks capped by it.
If the account is flat with no open orders, say "nothing to manage" and go to reporting. Do not invent work.

=== 4. RECORD ===

Commit state/ and push BY NAME: git push origin HEAD:claude/trading-agent-robinhood-cb9xo7. Confirm it is on origin.
New findings: append to state/reviews/2026-09-25-friday-queue.md, continuing the F-n sequence. Never renumber.
Do not promote, change or delete any rule. Do not edit engine/.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened ===

a. Write the report to state/reports/2026-09-25-relay-midday.md, commit it, push it by name, and confirm it is on origin.
b. Post it. Call fire_trigger (mcp__Claude_Code_Remote__fire_trigger, loading it with ToolSearch if needed) with trigger_id trig_01DcJrhKop6mfes4uutV3ChR and text = the report.

The first line must be exactly:  MIDDAY 2026-09-25 — ONE_LINE_HEADLINE
Then these headings, each filled in or marked "none":
 1. What occurred: what filled and at what price against the plan; what you managed and why
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift, positions with stop status and TIF, UNPROTECTED
 4. Plan for the rest of the day: what the 15:30 pre-close must decide, and your weekend-carry read per name
 5. Findings (F-n)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom
 8. Provenance: model and effort as read, and the commit pushed
Keep it under about 60 lines. If fire_trigger fails or is refused, record that in the committed file and in your final reply.
<!-- ---8<--- END MIDDAY ---8<--- -->

---

## 3. PRE-CLOSE — 15:30 ET (19:30 UTC), Opus runner

<!-- ---8<--- BEGIN PRE-CLOSE ---8<--- -->
Friday 2026-09-25, 15:30 ET. Pre-close, and the WEEKEND carry decision. This is 30 minutes before the bell. This firing opens no new risk.

YOU ARE UNATTENDED. Decide within the rules. Do not end a turn waiting for input.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
The path can change across a container re-provision, so never reuse one from this morning.
git pull origin claude/trading-agent-robinhood-cb9xo7
Read state/reports/2026-09-25-relay-*.md. The midday ran in a different session.
MODEL: read it again from the session record, and run echo $CLAUDE_EFFORT. Effort tracks the turn, not the session.
  python3 -m tools.model_check pre-close --model THE_MODEL_YOU_READ

=== 1. RECONCILE, CANCEL STALE ENTRIES, VERIFY PROTECTION ===

python3 -m tools.trading_day preclose
Report exactly what it cancelled, and its exit code. Unfilled same-day entries die here, before the closing auction.
python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash']); print('positions',a.positions()); print('orders',[(o['symbol'],o['side'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders(nested=True)]); print('stops',a.resting_stops()); print('UNPROTECTED:',a.positions_without_stops())"
UNPROTECTED must be []. `held` is a working stop. Every protective leg must read gtc. A "day" leg is cancelled at 16:00 with the position still open, so fix it or flatten before the bell, and lead with it.
WEEK_HALT or LOCKED means flatten at the next orderly opportunity.

=== 2. THE WEEKEND DECISION, explicitly, per position ===

The next open is Monday 2026-09-28 at 09:30 ET: about 65 hours and two nights of news. A stop is a fill instruction, not a price guarantee, and it does not hold through a gap. For each name, state whether you are carrying it and why. Price the gap risk at roughly twice the stop distance, and say whether a weekend warrants more and why. Carry only what you would put on fresh right now. "It is already on" is not a reason, and neither is avoiding a day trade. Give the total weekend gap risk in dollars and as a percentage of equity.

=== 3. FINAL MANAGEMENT PASS ===

Scale out at a hit target and move that stop to breakeven. Trail past +1R by 1.5 ATR. Exit a broken thesis. Never widen a stop. NO NEW ENTRIES.
If the account is flat with no open orders, say "nothing to carry" and go to reporting.

=== 4. RECORD ===

Commit state/ and push BY NAME: git push origin HEAD:claude/trading-agent-robinhood-cb9xo7. Confirm it is on origin.
Findings: append to state/reviews/2026-09-25-friday-queue.md, continuing the F-n sequence.
Do not promote, change or delete any rule. Do not edit engine/. Never write an --authorization.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened ===

a. Write the report to state/reports/2026-09-25-relay-preclose.md, commit it, push it by name, and confirm it is on origin.
b. Post it. Call fire_trigger (mcp__Claude_Code_Remote__fire_trigger) with trigger_id trig_01DcJrhKop6mfes4uutV3ChR and text = the report.

The first line must be exactly:  PRE-CLOSE 2026-09-25 — ONE_LINE_HEADLINE
Then these headings, each filled in or marked "none":
 1. What occurred: what preclose cancelled and its exit code; what you closed and why; the carry decision per name
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift, positions with stop status and TIF, UNPROTECTED, and weekend gap risk in $ and % of equity
 4. Plan for the rest of the day: what the 16:05 close must confirm
 5. Findings (F-n)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom
 8. Provenance: model and effort as read, and the commit pushed
Keep it under about 60 lines. If fire_trigger fails or is refused, record that in the committed file and in your final reply.
<!-- ---8<--- END PRE-CLOSE ---8<--- -->

---

## 4. CLOSE — 16:05 ET (20:05 UTC), Opus runner

<!-- ---8<--- BEGIN CLOSE ---8<--- -->
Friday 2026-09-25, 16:05 ET. Session close, and the close of Phase 2 week two. The market has just closed.

YOU ARE UNATTENDED. Decide within the rules. Do not end a turn waiting for input.

If the midday and pre-close firings did not run, that is because the open left nothing on the book and recalcitrantmaus's standing rule cancelled them. If you nevertheless hold a position that no pre-close reviewed, say so explicitly. An unreviewed weekend carry is a gap worth naming.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
git pull origin claude/trading-agent-robinhood-cb9xo7
Read today's state/reports/2026-09-25-relay-*.md.
MODEL: read it again from the session record, and run echo $CLAUDE_EFFORT.
  python3 -m tools.model_check session-close --model THE_MODEL_YOU_READ

=== 1. CLOSE THE DAY ===

python3 -m tools.trading_day close
Confirm from its output:
 a. CASH DRIFT: report it unconditionally, including zero, plus the cumulative figure for the day.
 b. cancel_unfilled_entries(): exactly what it cancelled.
 c. No protective leg stripped. A filled position must still have its stop.
python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print('UNPROTECTED:', a.positions_without_stops()); print([(o['symbol'],o['side'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders(nested=True)])"
UNPROTECTED must be []. Anything listed is unmanaged risk over a WEEKEND, so lead with it. Every leg must read gtc. `held` is a working stop.

=== 2. JOURNAL, REVIEW, WEEK ===

trade-journal: one entry per position closed today, covering the original thesis with its source URL, what actually happened, and whether the outcome came from process or luck. Flag loudly any WINNING trade taken off-plan. If nothing closed, write nothing and say so. Do not invent an entry.
python3 -m tools.review
python3 -m tools.trading_day week

Write state/reports/2026-09-25.md, plus state/reports/2026-09-25-summary.md in plain language for someone who has not been watching, covering the day and week two (2026-09-21 to 09-25).

WEEK TWO: report equity, the week's P&L and the honest gap to the +5% weekly hurdle. It is a hurdle rate, not a quota, and it is never closed with leverage. Report closed trades against the 30-trade exit criterion, and measured expectancy against +0.10R. If the account is flat because nothing traded, say that a flat account is an absence of evidence, not evidence that capital preservation works.

DO NOT run the weekly review. It is a blocking task that needs an --authorization in recalcitrantmaus's own words, and they are not here. Do not write one, and do not copy one out of state/authorizations.jsonl: reuse is refused, and a fabricated one would be a signed, dated lie in the repository. Instead, append a dated "Friday 2026-09-25 close" section to state/reviews/2026-W39-review-brief.md: the agenda a cleared, attended session should work through, pointing at state/reviews/2026-09-25-friday-queue.md.

Update HANDOFF.md's "Where we are" table and "The next thing to do" to the true state after today. Monday 2026-09-28 is UNARMED, and arming it is the first decision of the next attended session.

=== 3. RECORD ===

Commit everything in state/ and HANDOFF.md, and push BY NAME: git push origin HEAD:claude/trading-agent-robinhood-cb9xo7. Confirm it is on origin. The container is reclaimed, and anything not pushed did not happen.
Do not promote, change or delete any rule. Do not edit engine/.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened ===

a. Write the report to state/reports/2026-09-25-relay-close.md, commit it, push it by name, and confirm it is on origin.
b. Post it. Call fire_trigger (mcp__Claude_Code_Remote__fire_trigger) with trigger_id trig_01DcJrhKop6mfes4uutV3ChR and text = the report.

The first line must be exactly:  CLOSE 2026-09-25 — ONE_LINE_HEADLINE
Then these headings, each filled in or marked "none":
 1. What occurred today, across all four firings, and what fired for the first time
 2. What did not occur, and why. Anything that did not run is still unproven, so say so. A quiet day must not read as success.
 3. Account: equity, day P&L, week P&L, gap to +5%, cash drift, closed trades n/30, expectancy, what is carried over the weekend with its gap risk, and confirmation that it is protected
 4. Plan: what Monday needs, and that Monday is unarmed
 5. Findings (F-n), and every guardrail that fired or should have fired and did not
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom. Separate what needs recalcitrantmaus (decisions, authorizations, the weekly review) from what a session can do.
 8. Provenance: model and effort as read, and the commit pushed
Keep it under about 80 lines. If fire_trigger fails or is refused, record that in the committed file and in your final reply.
<!-- ---8<--- END CLOSE ---8<--- -->

---

## Watchdogs — fire into the arming session

<!-- ---8<--- BEGIN WD-OPEN ---8<--- -->
WATCHDOG — Friday 2026-09-25 OPEN (the 09:45 ET firing in Opus runner session_01Xn54wA68nkt7KHDaoj53RL). The relay handler deletes this trigger when the open's report arrives. If that report is already in this conversation, reply "open report already received" in one line and stop.

Otherwise the report has not arrived. Diagnose, read-only:
1. get_session session_01Xn54wA68nkt7KHDaoj53RL: status_bucket, post_turn_summary, last_served_model.
2. Locate the repo (REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"). Run git fetch origin claude/trading-agent-robinhood-cb9xo7, list today's commits on it, and look for state/reports/2026-09-25-relay-open.md.
3. Check the broker: python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash']); print('positions',a.positions()); print('orders',[(o['symbol'],o['side'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders(nested=True)]); print('UNPROTECTED:',a.positions_without_stops())"

Then:
- If the runner is still working, say so in one line, schedule one re-check 45 minutes out with send_later, and stop.
- If the report file is on the branch, the relay failed but the runner did not. Post the file's contents here as the open report.
- If there is neither, the open did not run or died silently. Report what you found.
- In either of the last two cases (never while the runner is still working), apply the standing rule: if the broker shows NO position AND NO open order, delete MIDDAY trig_01VQMv7HMhRVUBZqym2nsAsY, PRE-CLOSE trig_01RBYdpna33fdKvNet3GoMzn and WD-MIDDAY trig_01FRbJ8ysXYiP4ZKw8SecQ5M. CLOSE always runs. If anything filled or is resting, keep them.
- If UNPROTECTED is not empty, that is the emergency, so lead with it. Message the runner with a one-shot trigger bound to it (create_trigger with persistent_session_id session_01Xn54wA68nkt7KHDaoj53RL and run_once_at two minutes out; SendMessage cannot reach cloud sessions). Tell it to fix it or flatten it through the execution skill now, and to report back through the relay. Only if the runner cannot be reached may you flatten that position from here, and only through the repo's execution path, never improvised against the broker API.

Never open a position from this session. Never write an --authorization. Reply in at most ten lines.
<!-- ---8<--- END WD-OPEN ---8<--- -->

<!-- ---8<--- BEGIN WD-MIDDAY ---8<--- -->
WATCHDOG — Friday 2026-09-25 MIDDAY (the 12:30 ET firing in Sonnet runner session_01AvBRnTBfaiGqP8DvKpjsd1). The relay handler deletes this trigger when the midday report arrives, or when the standing rule cancels the midday. If either has already happened in this conversation, reply in one line and stop.

Otherwise diagnose, read-only: get_session session_01AvBRnTBfaiGqP8DvKpjsd1; git fetch origin claude/trading-agent-robinhood-cb9xo7 and look for state/reports/2026-09-25-relay-midday.md; then the broker check (equity, positions, open orders with TIF and status, UNPROTECTED).
- If the runner is still working, say so in one line, schedule one re-check 45 minutes out with send_later, and stop.
- If the report file is on the branch, post its contents here as the midday report.
- If neither, report what you found. The 15:30 pre-close in the Opus runner still runs and will see the book.
- If UNPROTECTED is not empty, lead with it. Message the Opus runner with a one-shot trigger bound to it (create_trigger with persistent_session_id session_01Xn54wA68nkt7KHDaoj53RL and run_once_at two minutes out; SendMessage cannot reach cloud sessions). Tell it to fix it or flatten it through the execution skill now. Only if no runner can be reached may you flatten from here, and only through the repo's execution path.

Never open a position from this session. Never write an --authorization. Reply in at most ten lines.
<!-- ---8<--- END WD-MIDDAY ---8<--- -->

<!-- ---8<--- BEGIN WD-CLOSE ---8<--- -->
WATCHDOG — Friday 2026-09-25 CLOSE (the 16:05 ET firing in Opus runner session_01Xn54wA68nkt7KHDaoj53RL, which also ran the 15:30 pre-close if it was not cancelled). The relay handler deletes this trigger when the close report arrives. If it is already in this conversation, reply "close report already received" in one line and stop.

Otherwise diagnose, read-only: get_session session_01Xn54wA68nkt7KHDaoj53RL; git fetch origin claude/trading-agent-robinhood-cb9xo7 and look for state/reports/2026-09-25-relay-preclose.md, 2026-09-25-relay-close.md, 2026-09-25.md and 2026-09-25-summary.md; then the broker check (equity, positions, open orders with TIF and status, UNPROTECTED).
- If the runner is still working, say so in one line, schedule one re-check 45 minutes out with send_later, and stop.
- If the report files are on the branch, post the close report's contents here.
- If the close did not run, create a one-shot trigger bound to the Opus runner (persistent_session_id session_01Xn54wA68nkt7KHDaoj53RL, run_once_at two minutes out) whose prompt is the CLOSE prompt, copied from docs/13a-routine-prompts-2026-09-25.md between BEGIN CLOSE and END CLOSE. SendMessage cannot reach cloud sessions. Report that you did so. Do not run the close from this session.
- Anything carried over the weekend with UNPROTECTED not empty is the emergency. Lead with it, and handle it as the other watchdogs do.

Then give recalcitrantmaus a closing line for the day: what is armed now (list_triggers should show nothing left enabled for 2026-09-25), and that Monday 2026-09-28 is unarmed.

Never open a position from this session. Never write an --authorization. Reply in at most twelve lines.
<!-- ---8<--- END WD-CLOSE ---8<--- -->

---

## CLOSE v2 — rebound to a fresh runner after F-1

The open was refused by the auto-mode classifier (F-1,
`state/reviews/2026-09-25-permissions-rca.md`). The original runner's
transcript carries two "read-only" rehearsal instructions, so the close was
moved to a fresh runner, and the prompt was rewritten so that every command
matches an allow rule exactly (docs/10 §7). The original CLOSE above is kept
for the record.

<!-- ---8<--- BEGIN CLOSE-V2 ---8<--- -->
Friday 2026-09-25, 16:05 ET. Session close, and the close of Phase 2 week two. The market has just closed.

YOU ARE UNATTENDED. Decide within the rules. Do not end a turn waiting for input. Midday and pre-close were cancelled under recalcitrantmaus's standing rule, because the open stood down (F-1) and left the account flat.

HOW TO RUN COMMANDS: run each command below as its OWN Bash call, exactly as written. Do not add cd, REPO=, &&, ;, a pipe or 2>&1. Every command here matches the repository's permission allowlist exactly, and a compound command does not. Read files with the Read tool, not cat. Do not use python3 -c.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

git rev-parse --show-toplevel
(If that is not the repository, do not cd or clone. Report it and stop.)
git pull origin claude/trading-agent-robinhood-cb9xo7
Read state/reports/2026-09-25-relay-open.md and state/reviews/2026-09-25-friday-queue.md.
MODEL: read it from the session record (get_session, session_id omitted), then:
python3 -m tools.model_check session-close --model THE_MODEL_YOU_READ

=== 1. CLOSE THE DAY ===

python3 -m tools.trading_day close
Confirm from its output: the CASH DRIFT figure, reported unconditionally, including zero; exactly what cancel_unfilled_entries() cancelled; and that no protective leg was stripped.
python3 -m tools.broker_check
Exit 1 means a position has no working stop over a WEEKEND. Lead with it. `held` is a working stop.

=== 2. JOURNAL, REVIEW, WEEK ===

trade-journal: one entry per position closed today. If nothing closed, write nothing and say so.
python3 -m tools.review
python3 -m tools.trading_day week
Write state/reports/2026-09-25.md, plus state/reports/2026-09-25-summary.md in plain language for someone who has not been watching, covering the day and week two (2026-09-21 to 09-25). Report equity, the week's P&L, the honest gap to the +5% hurdle (a hurdle rate, not a quota, never closed with leverage), closed trades against the 30-trade exit criterion, and expectancy against +0.10R. A flat account is an absence of evidence, not evidence that capital preservation works.
DO NOT run the weekly review. It needs an --authorization in recalcitrantmaus's own words, and they are not here. Never write one. Instead, append a dated "Friday 2026-09-25 close" section to state/reviews/2026-W39-review-brief.md: the agenda for a cleared, attended session, pointing at state/reviews/2026-09-25-friday-queue.md, 2026-09-25-permissions-rca.md and 2026-09-25-effort-design-notes.md.
Update HANDOFF.md's "Where we are" and "The next thing to do" to the true state after today. Monday 2026-09-28 is UNARMED.
Findings: append to state/reviews/2026-09-25-friday-queue.md, continuing the F-n sequence. For each command above, record whether it ran or was refused by the permission layer. That record is the test of the F-1 fix.

=== 3. RECORD ===

git add state HANDOFF.md
git commit -m "Close 2026-09-25: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
Do not promote, change or delete any rule. Do not edit engine/.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened ===

a. Write the report to state/reports/2026-09-25-relay-close.md. Commit it and push it, using the three git commands above.
b. Call fire_trigger (mcp__Claude_Code_Remote__fire_trigger) with trigger_id trig_01DcJrhKop6mfes4uutV3ChR and text = the report.
First line exactly:  CLOSE 2026-09-25 — ONE_LINE_HEADLINE
Then these headings, each filled in or marked "none":
 1. What occurred
 2. What did not occur, and why
 3. Account: equity, day and week P&L, gap to +5%, cash drift, closed trades n/30, expectancy, and what is carried with its protection
 4. Plan: Monday is unarmed
 5. Findings (F-n), including the per-command permission record
 6. Bugs
 7. Still to be completed, and by whom
 8. Provenance: model and effort, and the commit
<!-- ---8<--- END CLOSE-V2 ---8<--- -->

### State after the rebinding (2026-09-25 ~11:45 ET)

| | |
|---|---|
| Deleted under the standing rule (flat after the open) | MIDDAY `trig_01VQMv7HMhRVUBZqym2nsAsY`, PRE-CLOSE `trig_01RBYdpna33fdKvNet3GoMzn`, WD-MIDDAY `trig_01FRbJ8ysXYiP4ZKw8SecQ5M` |
| Deleted and replaced | CLOSE `trig_01K8aKJt8rf2wDnVGpuoJsPU`, whose runner's transcript was contaminated |
| Runner v2 | `session_01KEoB4VKvJSkpL6N5uqC3z1`, Opus 5.5. First turn: F1-TEST, a live run of each command form, including `trading_day open` |
| CLOSE v2 | `trig_01CL9eMLcRw4M3Qg8KoQF5jj`, 20:05Z, bound to runner v2 |
| WD-CLOSE, relay | same ids, prompts updated to runner v2 and broker_check |
