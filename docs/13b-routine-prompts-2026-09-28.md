# Routine prompts — Monday 2026-09-28

Armed 2026-09-26 by the attended weekly-review session (the "arming session",
`session_01YGq4H9eezU7hawFM3bRgE2`), at recalcitrantmaus's instruction. Reports come back
into that session. `list_triggers` is the truth for what is armed.

## Shape, and what changed from Friday

| ET | UTC | firing | trigger |
|---|---|---|---|
| 09:45 | 13:45 | OPEN | `trig_01EDA1ThFwgtpqLnyJF5kz2B` |
| 12:30 | 16:30 | MIDDAY | `trig_01Vqm4bGXThWmna8kBLMyJYQ` |
| 15:30 | 19:30 | PRE-CLOSE | `trig_01WCnaAyNjRjfmvKmxZCYrV8` |
| 16:05 | 20:05 | CLOSE | `trig_01SGcBMeCdBAdhH1GwVJs7Bp` |

- **One runner**, Opus 5.5: `session_013eAnYvR3gjvfcQY6u7dip1`. The midday is
  Opus too, since recalcitrantmaus moved it off Sonnet on Friday.
- **Created with no first prompt.** Nothing, including a rehearsal, sits in its
  transcript ahead of the open (docs/10 section 7).
- **One command per Bash call**, spelled as the allowlist spells it. No
  `python3 -c`: broker state comes from `tools.broker_check`, and the
  premarket macro step from `tools.macro`.
- **Report-back by a scheduled one-shot trigger** bound to the arming session
  (`create_trigger`, `run_once_at` two minutes out). **Never `fire_trigger`**,
  which starts a new, unread session (`state/reviews/2026-09-26-rca-relay.md`).
  The runner records the call's result in the committed report.
- **Effort caveat:** a `create_session` runner has no effort setting of its
  own. Setting its picker to Extra high, and toggling it, is the only lever
  (E-1). Trading tasks warn and continue below the floor.

## Relay handler (followed by the arming session when a report arrives)

1. The first line names the firing.
2. Verify, read-only: `git fetch origin claude/trading-agent-robinhood-cb9xo7`
   (the runner's commit is on the branch), and `python3 -m tools.broker_check`.
   Name any disagreement with the report.
3. Delete that firing's watchdog: OPEN -> WD-OPEN `trig_01AG7pMmepXKKnFSfbTCMp8U`;
   MIDDAY -> WD-MIDDAY `trig_01794T8Eosz1hgEjanrC5Gm8`; CLOSE -> WD-CLOSE
   `trig_012rfqNtC5dr6Xqq2Tur5AL9`. PRE-CLOSE has none.
4. OPEN only, recalcitrantmaus's standing rule: if the broker shows NO position AND NO
   open order, delete MIDDAY, PRE-CLOSE and WD-MIDDAY. The CLOSE always runs.
5. broker_check exit 1: lead with it, and message the runner with a one-shot
   trigger bound to it, two minutes out, to fix or flatten through the
   execution skill.
6. Reply in at most eight lines. Never trade from the arming session, never
   edit engine/, never write an --authorization.

## Watchdogs (scheduled into the arming session)

| ET | UTC | watchdog | trigger |
|---|---|---|---|
| 11:15 | 15:15 | WD-OPEN | `trig_01AG7pMmepXKKnFSfbTCMp8U` |
| 13:45 | 17:45 | WD-MIDDAY | `trig_01794T8Eosz1hgEjanrC5Gm8` |
| 17:15 | 21:15 | WD-CLOSE | `trig_012rfqNtC5dr6Xqq2Tur5AL9` |

A watchdog that fires means its report did not arrive. It diagnoses from the
session record, git and the broker, and never trades.

---

## OPEN

<!-- ---8<--- BEGIN OPEN ---8<--- -->
Monday 2026-09-28, 09:45 ET. Session open, and the first day of ISO week 2026-W40. The market opened 15 minutes ago.

YOU ARE UNATTENDED. recalcitrantmaus is not available during the session. Nobody will answer a question, so decide within the rules, or stand down and record why. Do not end a turn waiting for input.

HOW TO RUN COMMANDS (F-1, docs/10 section 7): run each command as its OWN Bash call, exactly as written. Do not add cd, REPO=, &&, ;, a pipe or 2>&1. Read files with the Read tool. Never use python3 -c. Every command here matches the repository's allowlist exactly, and a compound command does not. If the permission layer refuses a command, do not retry it in another form. Record the refusal verbatim and continue. A refusal at step 0 means stop and report.

The rule that outranks everything: the model decides what to trade, and code decides whether it is allowed. If RiskOfficer rejects an order, record the rejection and move on. Never reshape the order until it passes.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

git rev-parse --show-toplevel
(If that is not the repository, do not cd or clone. Report it and stop.)
git pull origin claude/trading-agent-robinhood-cb9xo7
Read CLAUDE.md and HANDOFF.md with the Read tool.
python3 -m tools.preflight_phase2
python3 -m tools.trading_day open
python3 -m tools.netcheck
python3 -m tools.status
python3 -m tools.broker_check
Any non-zero exit from preflight_phase2 or trading_day open means DO NOT TRADE.
MODEL: read it from the session record (get_session, session_id omitted). Then:
python3 -m tools.model_check premarket-brief --model THE_MODEL_YOU_READ
python3 -m tools.model_check trade-plan --model THE_MODEL_YOU_READ
A downgrade warns and continues. Record it. Never pass --authorization or --effort.

=== 1. THE TRADING SET ===

Run premarket-brief (its macro step is python3 -m tools.macro), then news-intel, then trade-plan, then execution:
python3 -m tools.screen
python3 -m tools.paper_session --submit
Run tools.screen BEFORE concluding there is no setup, and state the denominator. An empty plan is binding: trade nothing.

What changed on 2026-09-26 (read docs/04-lessons.md entries of that date):
 a. Targets stay MANDATORY at expected R >= 1.5 (D-24 was declined by recalcitrantmaus). Do not propose without a target.
 b. The day-trade budget no longer binds (W-3: this is a cash account). Day trades are counted and shown for information only. T+1 settled cash is the constraint, and the engine gates it.
 c. A sell must reduce a position held (M-7). Shorts are refused.
 d. `held` is the normal working status of a resting stop. Do not flatten on it.
 e. The price NOW is adapter.last_trade(). Bars are completed sessions. Cross-check every price you would trade; more than 50bps apart means stand down on that symbol.
 f. Size tapers 2% / 1% / 0.5% / 0.25%, with an aggregate open-risk cap of 4%. A tapered refusal is the rule working.
 g. No crypto (no stop attaches). Options are locked.
Every factual claim carries a source URL. Never invent a price or a citation. WRITE THE PLAN OUT PER NAME, including the refusals and which constraint bound each one.

=== 2. RECORD ===

git add state data
git commit -m "Open 2026-09-28: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
New findings: state/reviews/2026-09-28-queue-g.md, as G-1, G-2, and so on, shared by all of today's firings. Never renumber.
Do not run the weekly review. Do not change any rule. Do not edit engine/.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened, including a stop at step 0 ===

a. Write the report to state/reports/2026-09-28-relay-open.md, then:
git add state
git commit -m "Mon 2026-09-28 open: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
b. Get the time: date -u +%Y-%m-%dT%H:%M:%SZ
c. Call create_trigger (mcp__Claude_Code_Remote__create_trigger) with persistent_session_id session_01YGq4H9eezU7hawFM3bRgE2, run_once_at = that time plus 2 minutes (RFC3339, UTC), initiation own_followup, name "Mon 2026-09-28 OPEN report", and prompt = the report. Do NOT use fire_trigger. It starts a new, unread session instead of delivering (state/reviews/2026-09-26-rca-relay.md).
d. Append the create_trigger result to the report file (the trigger id, or the error verbatim), then run the three git commands again.

The report's first line must be exactly:
RELAY FOR THE ARMING SESSION — OPEN 2026-09-28 — ONE_LINE_HEADLINE. Handle per docs/13b-routine-prompts-2026-09-28.md "Relay handler".
Then these headings, each filled in or marked "none":
 1. What occurred
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift (always, including zero), positions with stop status, broker_check exit code
 4. Plan for the rest of the day
 5. Findings (G-n, in state/reviews/2026-09-28-queue-g.md)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom (a later firing, or recalcitrantmaus)
 8. Provenance: model and CLAUDE_EFFORT as read, the commit pushed, and the command permission record (ran or refused, per command)
Keep it under about 60 lines. Detail belongs in the committed files.
In section 2 of the report, name any of these that ran against reality for the first time: an open that SUBMITTED under the one-command-per-call form; the posture gate blocking a real order; an empty plan binding against a scanner that disagrees. In section 4, say whether the standing rule applies (nothing filled and nothing resting means midday and pre-close are cancelled, and the close still runs).
<!-- ---8<--- END OPEN ---8<--- -->

---

## MIDDAY

<!-- ---8<--- BEGIN MIDDAY ---8<--- -->
Monday 2026-09-28, 12:30 ET. Midday management. This firing MANAGES existing risk. It opens no new risk, for any reason.

YOU ARE UNATTENDED. recalcitrantmaus is not available during the session. Nobody will answer a question, so decide within the rules, or stand down and record why. Do not end a turn waiting for input.

HOW TO RUN COMMANDS (F-1, docs/10 section 7): run each command as its OWN Bash call, exactly as written. Do not add cd, REPO=, &&, ;, a pipe or 2>&1. Read files with the Read tool. Never use python3 -c. Every command here matches the repository's allowlist exactly, and a compound command does not. If the permission layer refuses a command, do not retry it in another form. Record the refusal verbatim and continue. A refusal at step 0 means stop and report.

This firing exists only because the open left something on the book (a position, or an entry still resting).

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

git rev-parse --show-toplevel
git pull origin claude/trading-agent-robinhood-cb9xo7
Read state/reports/2026-09-28-relay-open.md and today's plan in state/plans/2026-09-28.* with the Read tool.
MODEL: get_session (session_id omitted), then:
python3 -m tools.model_check execution --model THE_MODEL_YOU_READ

=== 1. RECONCILE AND CHECK PROTECTION ===

python3 -m tools.trading_day open
python3 -m tools.broker_check
broker_check exit 1 means a position has no working stop. Fix it or flatten it through the execution skill before anything else, and lead the report with it. `held` legs are working stops.
Report the cash-drift line unconditionally.

=== 2. VERIFY THE MORNING'S SUBMIT ===

A filled order's state/fills.jsonl row carries the broker's price (B-15). Report slippage against the plan. An unfilled order is in ledger working_orders with no fill row. Every protective leg reads gtc.

=== 3. MANAGE ===

Scale out at the first target and move that stop to breakeven. Trail the remainder past +1R by 1.5 ATR. Exit a broken thesis. NEVER widen a stop, average down or add. NO NEW ENTRIES. Flat with no orders means "nothing to manage": go to reporting.

=== 4. RECORD ===

git add state
git commit -m "Midday 2026-09-28: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
Findings go in state/reviews/2026-09-28-queue-g.md, continuing the G-n sequence.

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened, including a stop at step 0 ===

a. Write the report to state/reports/2026-09-28-relay-midday.md, then:
git add state
git commit -m "Mon 2026-09-28 midday: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
b. Get the time: date -u +%Y-%m-%dT%H:%M:%SZ
c. Call create_trigger (mcp__Claude_Code_Remote__create_trigger) with persistent_session_id session_01YGq4H9eezU7hawFM3bRgE2, run_once_at = that time plus 2 minutes (RFC3339, UTC), initiation own_followup, name "Mon 2026-09-28 MIDDAY report", and prompt = the report. Do NOT use fire_trigger. It starts a new, unread session instead of delivering (state/reviews/2026-09-26-rca-relay.md).
d. Append the create_trigger result to the report file (the trigger id, or the error verbatim), then run the three git commands again.

The report's first line must be exactly:
RELAY FOR THE ARMING SESSION — MIDDAY 2026-09-28 — ONE_LINE_HEADLINE. Handle per docs/13b-routine-prompts-2026-09-28.md "Relay handler".
Then these headings, each filled in or marked "none":
 1. What occurred
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift (always, including zero), positions with stop status, broker_check exit code
 4. Plan for the rest of the day
 5. Findings (G-n, in state/reviews/2026-09-28-queue-g.md)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom (a later firing, or recalcitrantmaus)
 8. Provenance: model and CLAUDE_EFFORT as read, the commit pushed, and the command permission record (ran or refused, per command)
Keep it under about 60 lines. Detail belongs in the committed files.
<!-- ---8<--- END MIDDAY ---8<--- -->

---

## PRE-CLOSE

<!-- ---8<--- BEGIN PRE-CLOSE ---8<--- -->
Monday 2026-09-28, 15:30 ET. Pre-close and the overnight carry decision. This is 30 minutes before the bell. This firing opens no new risk.

YOU ARE UNATTENDED. recalcitrantmaus is not available during the session. Nobody will answer a question, so decide within the rules, or stand down and record why. Do not end a turn waiting for input.

HOW TO RUN COMMANDS (F-1, docs/10 section 7): run each command as its OWN Bash call, exactly as written. Do not add cd, REPO=, &&, ;, a pipe or 2>&1. Read files with the Read tool. Never use python3 -c. Every command here matches the repository's allowlist exactly, and a compound command does not. If the permission layer refuses a command, do not retry it in another form. Record the refusal verbatim and continue. A refusal at step 0 means stop and report.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

git rev-parse --show-toplevel
git pull origin claude/trading-agent-robinhood-cb9xo7
Read today's state/reports/2026-09-28-relay-*.md with the Read tool.
MODEL: get_session (session_id omitted), then:
python3 -m tools.model_check pre-close --model THE_MODEL_YOU_READ

=== 1. CANCEL STALE ENTRIES, VERIFY PROTECTION ===

python3 -m tools.trading_day preclose
Report what it cancelled, and its exit code.
python3 -m tools.broker_check
Exit 1 is the emergency: fix it or flatten before the bell, and lead with it. Every protective leg must read gtc.

=== 2. THE OVERNIGHT DECISION, per position ===

A stop does not hold through a gap. For each name, state whether you are carrying it and why, and price the gap risk at about twice the stop distance. Carry only what you would put on fresh right now. Give the total overnight gap risk in $ and as a % of equity.

=== 3. FINAL MANAGEMENT PASS ===

Scale out at a hit target, trail past +1R, exit a broken thesis. Never widen a stop. NO NEW ENTRIES.

=== 4. RECORD ===

git add state
git commit -m "Pre-close 2026-09-28: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened, including a stop at step 0 ===

a. Write the report to state/reports/2026-09-28-relay-preclose.md, then:
git add state
git commit -m "Mon 2026-09-28 preclose: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
b. Get the time: date -u +%Y-%m-%dT%H:%M:%SZ
c. Call create_trigger (mcp__Claude_Code_Remote__create_trigger) with persistent_session_id session_01YGq4H9eezU7hawFM3bRgE2, run_once_at = that time plus 2 minutes (RFC3339, UTC), initiation own_followup, name "Mon 2026-09-28 PRE-CLOSE report", and prompt = the report. Do NOT use fire_trigger. It starts a new, unread session instead of delivering (state/reviews/2026-09-26-rca-relay.md).
d. Append the create_trigger result to the report file (the trigger id, or the error verbatim), then run the three git commands again.

The report's first line must be exactly:
RELAY FOR THE ARMING SESSION — PRE-CLOSE 2026-09-28 — ONE_LINE_HEADLINE. Handle per docs/13b-routine-prompts-2026-09-28.md "Relay handler".
Then these headings, each filled in or marked "none":
 1. What occurred
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift (always, including zero), positions with stop status, broker_check exit code
 4. Plan for the rest of the day
 5. Findings (G-n, in state/reviews/2026-09-28-queue-g.md)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom (a later firing, or recalcitrantmaus)
 8. Provenance: model and CLAUDE_EFFORT as read, the commit pushed, and the command permission record (ran or refused, per command)
Keep it under about 60 lines. Detail belongs in the committed files.
<!-- ---8<--- END PRE-CLOSE ---8<--- -->

---

## CLOSE

<!-- ---8<--- BEGIN CLOSE ---8<--- -->
Monday 2026-09-28, 16:05 ET. Session close. The market has just closed.

YOU ARE UNATTENDED. recalcitrantmaus is not available during the session. Nobody will answer a question, so decide within the rules, or stand down and record why. Do not end a turn waiting for input.

HOW TO RUN COMMANDS (F-1, docs/10 section 7): run each command as its OWN Bash call, exactly as written. Do not add cd, REPO=, &&, ;, a pipe or 2>&1. Read files with the Read tool. Never use python3 -c. Every command here matches the repository's allowlist exactly, and a compound command does not. If the permission layer refuses a command, do not retry it in another form. Record the refusal verbatim and continue. A refusal at step 0 means stop and report.

If midday and pre-close did not run, the open left nothing on the book and recalcitrantmaus's standing rule cancelled them. If you nevertheless hold a position no pre-close reviewed, say so explicitly.

=== 0. ENVIRONMENT. If any of this fails, stop and go straight to the LAST section ===

git rev-parse --show-toplevel
git pull origin claude/trading-agent-robinhood-cb9xo7
Read today's state/reports/2026-09-28-relay-*.md with the Read tool.
MODEL: get_session (session_id omitted), then:
python3 -m tools.model_check session-close --model THE_MODEL_YOU_READ

=== 1. CLOSE THE DAY ===

python3 -m tools.trading_day close
Confirm from its output: the cash drift (always, including zero), what it cancelled, and that no protective leg was stripped.
python3 -m tools.broker_check
Exit 1 is the emergency. Lead with it.

=== 2. JOURNAL AND REVIEW ===

trade-journal: one entry per position closed today, with the thesis and its source URL, what happened, and whether the outcome was process or luck. Nothing closed means write nothing, and say so.
python3 -m tools.review
Write state/reports/2026-09-28.md, plus state/reports/2026-09-28-summary.md in plain language. A flat account is an absence of evidence, not proof that capital preservation works.
Update HANDOFF.md "Where we are" and "The next thing to do" to the true state. Tuesday 2026-09-29 is UNARMED.
Do not run the weekly review. Do not change any rule. Never write an --authorization.

=== 3. RECORD ===

git add state HANDOFF.md
git commit -m "Close 2026-09-28: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7

=== LAST: REPORT BACK TO THE ARMING SESSION. Do this whatever happened, including a stop at step 0 ===

a. Write the report to state/reports/2026-09-28-relay-close.md, then:
git add state
git commit -m "Mon 2026-09-28 close: ONE_LINE_SUMMARY"
git push origin HEAD:claude/trading-agent-robinhood-cb9xo7
b. Get the time: date -u +%Y-%m-%dT%H:%M:%SZ
c. Call create_trigger (mcp__Claude_Code_Remote__create_trigger) with persistent_session_id session_01YGq4H9eezU7hawFM3bRgE2, run_once_at = that time plus 2 minutes (RFC3339, UTC), initiation own_followup, name "Mon 2026-09-28 CLOSE report", and prompt = the report. Do NOT use fire_trigger. It starts a new, unread session instead of delivering (state/reviews/2026-09-26-rca-relay.md).
d. Append the create_trigger result to the report file (the trigger id, or the error verbatim), then run the three git commands again.

The report's first line must be exactly:
RELAY FOR THE ARMING SESSION — CLOSE 2026-09-28 — ONE_LINE_HEADLINE. Handle per docs/13b-routine-prompts-2026-09-28.md "Relay handler".
Then these headings, each filled in or marked "none":
 1. What occurred
 2. What did not occur, and why
 3. Account: equity, day P&L, cash drift (always, including zero), positions with stop status, broker_check exit code
 4. Plan for the rest of the day
 5. Findings (G-n, in state/reviews/2026-09-28-queue-g.md)
 6. Bugs (file:line where known)
 7. Still to be completed, and by whom (a later firing, or recalcitrantmaus)
 8. Provenance: model and CLAUDE_EFFORT as read, the commit pushed, and the command permission record (ran or refused, per command)
Keep it under about 60 lines. Detail belongs in the committed files.
<!-- ---8<--- END CLOSE ---8<--- -->
