# Weekly review — week ending Friday 2026-09-25 (ISO 2026-W39)

**Status: agenda only. The review itself has not been run yet.** It runs in an
attended session, cleared by `model_check weekly-review` with the model read
from the session record and an `--authorization` in recalcitrantmaus's own words. Its
decisions are appended below as a dated section.

Everything under "Agenda" was written by unattended sessions that were not
cleared to run the review. That is why they call it "not the weekly review".
That still holds for any unattended session, and it is accurate for when each
section was written.

---

## Agenda — Monday 2026-09-21, 16:15 ET (unattended close session)

**This is not the weekly review.** It is the agenda for one, assembled by the
Monday close session, which is unattended and **not cleared** to run it.

```
python3 -m tools.model_check weekly-review   ->  exit 1
  !! 'weekly-review' is blocking and the running model is UNVERIFIED: the value
     'claude-sonnet-5' came from TRADING_AGENT_MODEL, an ENVIRONMENT-level
     default ... Refusing rather than guessing.
```

`--model` was deliberately **not** passed. HANDOFF is explicit that the override
is honest only from a present human who has verified the value and **never in an
unattended session**, and this session cannot measure its own model. It would
also be blocked on effort: the floor is Opus @ xhigh and the harness reports
`CLAUDE_EFFORT=high` (queue item 17).

**Nothing below has been actioned.** No rule was promoted, changed or deleted.
`engine/`, `docs/04-lessons.md` and every `SKILL.md` are untouched tonight.

## Who must run this

Opus tier at xhigh effort, with the model **confirmed out of band** and passed
explicitly, per HANDOFF "Model routing in practice". Read queue item 17 before
trusting the gate's own answer about effort.

## The standing fact that frames every item

**Zero closed trades. Ever.** Six sessions, two live submits, no fill. The
account has never held a position. Every question below is therefore a question
about *controls and process*, and **not one of them can be answered with trade
evidence** — the CLAUDE.md standard for changing a rule (five consistent closed
trades, or a backtest showing a better median without a worse ruin rate) is
unmet for every behavioural item here. A reviewer who changes strategy rules
this week is changing them on zero data.

## Decide first — the two that will recur before any trade does

1. **Item 14/15 — `outcome_branch` on the Routines.** Today's prompts carried an
   explicit `git push origin HEAD:<branch>` and it worked, three firings for
   three. It also did not stop the harness creating its own derived branch each
   time: today produced four orphans (`magical-knuth-khwjye`,
   `confident-ritchie-k7cef8`, `wizardly-carson-5qjgn5`, and this session's).
   The prompt line is a mitigation that must be re-remembered every firing; an
   `outcome_branch` set once at Routine creation is the invariant. **This is the
   pattern the project keeps rediscovering: a capital-adjacent invariant living
   in prose.** Decide the durable fix, then do item 15's per-branch merge-base
   check and clean up.
2. **Item 16 — `cancel_unfilled_entries()` is correctly scoped and wrongly
   timed.** It runs at 16:05, *after* the closing cross, which is the single
   print most likely to fill a resting limit. Today it was covered only because
   the 15:30 session chose to cancel ETHA by hand at 15:33. That is a guardrail
   whose coverage depended on a judgement call, which is the definition of a
   control that is not one. Either move it into the pre-close firing or make it
   a rule that any unfilled same-day entry dies before the auction. **Code plus
   a test, per CLAUDE.md — not a prompt instruction.**

## The controls findings from today

3. **Item 17 (new, high) — the effort gate is over-claiming.** Both inputs to
   the binding routing control are now unmeasured operator declarations, and
   both fail in the permissive direction. The specific trap: an attended session
   correctly passes `--model claude-opus-5`, and the effort check then clears on
   `TRADING_AGENT_EFFORT=xhigh` while the session runs at `high` — the exact
   configuration HANDOFF's table calls "the worst of the four". Proposed:
   `current_effort()` cross-checks against `CLAUDE_EFFORT` and refuses a
   blocking task on disagreement, mirroring what `model_and_source()` already
   does for the model. This was already on HANDOFF's open-questions list; today
   is the evidence for taking it.
4. **Items 18 and 20 (new) — the week window and the calendar.** `cmd_week`
   counts `days[-5:]` while dividing by a calendar-anchored `week_start_equity`,
   and the `days` list still takes rows on non-trading days. Both are harmless
   at $299.99 flat and both become wrong-but-plausible the first week with real
   P&L. Item 8's Alpaca calendar endpoint fixes the root of both.
5. **B-16 is still unverified, second consecutive zero-fill session.** Legs read
   `gtc` while resting for five and a half hours, which proves nothing
   regressed. Verification needs a leg **promoted from `held` to `new` by a
   parent fill** — Alpaca re-issues legs as standalone orders at that moment,
   and that re-issue, not the submit, is where a `day` TIF could appear.
6. **The `cancel_unfilled_entries()` leg-safety property has never run live**
   (close-session check (c)). Unit tests and the `legs`/`type` guard cover it;
   the broker never has.
7. **Item 4 — D-17's fractional probe still needs re-running.** The rejection
   message changed underneath it on 2026-09-18 and the split probe has not been
   run. D-17 carries the $75 ceiling, which carries the universe argument.

## The strategy questions — do not settle these this week

8. **Item 2 — pullback entry vs the study's next-open chase.** Today is one
   clean demonstration: the signal was right (ETHA +4.8%), the limit sat 2.2%
   below the market all day, and the account participated in none of it. That is
   evidence about this entry style and **not** proof the chase is better. One
   non-fill. `docs/15` was already not statistically significant; this weakens
   it rather than resolving it. Make the study and the live path match *after*
   deciding which one we want, not by drifting.
9. **Item 6 — D-24** (no-target exit, 20-day time stop) remains deferred and
   still needs the `max_holding_days` enforcement that does not exist.
10. **Item 7 — a short entry bypasses the risk gate.** Latent, unchanged, and
    must be fixed **before** any downside strategy is written, not after.
11. **Item 12's precedent** — "carry only what you would put on fresh right
    now", used to cancel ETHA — is recorded as a precedent and is **not yet a
    rule**. Promoting it is item 16's decision, and it needs a test.

## The one question none of this answers

Whether model-generated theses have positive expectancy. Six sessions in, the
sample is still empty, and the week's output is again infrastructure.
**Infrastructure is not the Phase 2 exit criterion.** The most useful thing a
reviewer can decide is not which rule to change but what would have to happen
for this system to take, and close, a trade.

## Agenda — Friday 2026-09-25 close (unattended close runner)

**This is still not the weekly review.** Runner v2 (`session_01KEoB4VKvJSkpL6N5uqC3z1`) is unattended, and
`model_check session-close` read harness effort **medium**, below xhigh. The weekly review also needs an
`--authorization` in recalcitrantmaus's own words. No authorization was written. No rule was promoted, changed or deleted.
`engine/` was not touched.

**The week in one line:** $299.62, -0.12% (-$0.37) for the week, gap to +5% is -5.12%, 1/30 closed trades,
-0.139R against +0.10R. Phase 2 exit criteria met: 3/5. The account is flat into the weekend with nothing unprotected.

Read these first:

- `state/reviews/2026-09-25-queue-f.md`: F-1 (the open refused at step 0), F-2 (the live test: every
  command ran) and F-3 (the close: every command ran, plus the smaller findings).
- `state/reviews/2026-09-25-rca-permissions.md`: why the classifier, not the allowlist, decided F-1.
- `state/reviews/2026-09-25-design-effort.md`: how effort is read and gated for unattended runners.

Decide, in this order:

1. **Arm Monday 2026-09-28 or not.** The one-command-per-call form survived a full close. It has **not** yet survived an
   open that submits an order. That order path is the part F-1 actually blocked.
2. **Effort.** Both runner v2 checks today read `medium` against an xhigh floor, while the environment declares xhigh.
   The open runner's record says xhigh. The declaration and the harness disagree, and the runners are below
   the floor for the open and the close. See the effort design notes.
3. **F-3 items:** `cmd_week`'s "costs below gains" passes as `$0.00 <= max(-$0.37, 0)` on a losing record. This is a
   borderline vacuous pass, shape 2 in `docs/04-lessons.md`. Also, `trading_day close` says nothing when
   `cancel_unfilled_entries()` cancels nothing, and `open` prints no cash-drift line.
4. Carried from above and still open: item 2 (entry style), M-7 (short entry bypasses the gate), D-24.

---

## Attended session, 2026-09-26: authorizations given, not yet used

recalcitrantmaus, verbatim, in `session_01YGq4H9eezU7hawFM3bRgE2`:

1. "I authorize you, Claude, to run the weekly review on Opus 5 Extra"
2. "I authorize the design/build/test efforts to be executed in the engine for the effort gate design"
3. "I authorize the design/build/test efforts to be executed in the engine for the day-trade budget counting fix"
4. "I authorize the design/build/test efforts to be executed in the engine for the short entry fix"
5. "I authorize the design/build/test efforts to be executed in the engine for the target treatment"

**None of them has been passed to `model_check` yet, so none is recorded in
`state/authorizations.jsonl`.** The gate cannot clear in this session:

- the session record reads `effort_level: xhigh` (the picker is at Extra high)
- the harness reports this turn at `CLAUDE_EFFORT=medium`
- `model_check weekly-review --at-write --started-at xhigh` exits 1
  ("requires effort >= xhigh; this turn is running medium")

Using an authorization now would record a clearance that the at-write
re-check refuses one step later. It would also burn the authorization, which
is single-use. The authorizations are held here until a turn reads `xhigh`.
This is the same disagreement as `2026-09-25-design-effort.md` #4, now
observed in an attended session with the picker confirmed at Extra high.

---

## THE WEEKLY REVIEW — run 2026-09-26, attended

Cleared by `model_check weekly-review --model claude-opus-5-5` at effort xhigh,
with recalcitrantmaus's authorization recorded in `state/authorizations.jsonl`
(2026-09-26T19:32:17Z). The effort floor was re-checked immediately before
this write (`--at-write`, exit 0).

**How the effort block cleared (evidence for the effort-gate design).** For
three turns the session record read `effort_level: xhigh`, while the harness
served each turn at `CLAUDE_EFFORT=medium`, and the session's
`flag_settings_seq` stayed at 14. recalcitrantmaus closed a VS Code client attached to the
session and toggled the web picker away from Extra high and back.
`flag_settings_seq` then moved to 923, and the next turn read `xhigh`. The
picker's *displayed* value was never the served value. A fresh write of the
setting was what reached the turns.

### The seven questions (trade-journal skill)

`python3 -m tools.review --week`: 1 trade, 0W / 1L, net -$0.37, costs $0.00,
expectancy -0.139R.

1. **Weekly return against the 5% hurdle:** -0.12% (-$0.37 on $299.99). The gap is
   **-5.12 points**. It is a hurdle, not a quota. Nothing is closed with leverage.
2. **Win rate, average win/loss in R, profit factor:** 0%, no wins, -0.139R, 0.0.
   One trade measures nothing.
3. **Costs as a percentage of starting equity:** 0.00% (commission-free paper).
   Costs did not exceed gains. There were no gains, and after F-3 the exit
   criterion now says so instead of passing.
4. **Largest drawdown:** 0.13% from the $300.00 peak. Its cause was the DT
   flatten on 2026-09-23. **That was a process error, not a stop.** `held` was
   misread as "stop not live". Holding would have cost about -0.075R instead
   of -0.139R.
5. **Trades graded bad-process:** one, the DT exit (T-17). The common factor
   is reasoning from **silence in a reference**: `held` was absent from
   Alpaca's status list, and absence was read as malfunction. The entry was
   on-plan.
6. **Rules promoted or deleted this week**, from `state/authorizations.jsonl`:
   M-22 (the attendance gate became a recorded authorization), T-1 (a 4%
   aggregate open-risk cap), the model schedule (Opus floors at the open, the
   pre-close and the close), the size taper (`correlated_risk_decay` 0.5),
   T-9 (trading dates keyed to ET), T-10 (the effort re-check at the write),
   and the `held` correction (reverted in full on 2026-09-24). Today's four
   engine items are recorded below as each one lands. **None was deleted.**
7. **Is the measured edge positive?** No: -0.139R. But n = 1, and the
   skill's size-cut rule starts at 20 trades. **The edge is unmeasured, not
   negative.** Phase 2 has produced one closed trade in two weeks. That, not
   any single rule, is the week's finding.

### The agenda, item by item

| # | item | status after this week | evidence |
|---|---|---|---|
| 1 | `outcome_branch` on Routines | **resolved**: runners are created with `outcome_branch` set | 2026-09-22 onward; no new orphans; `claude/wizardly-carson-5qjgn5` deleted by recalcitrantmaus 2026-09-26 |
| 2 | `cancel_unfilled_entries()` timing | **resolved**: `trading_day preclose` cancels entries before the auction | `054567d` (M-16), live 2026-09-23 |
| 3 | effort gate over-claims | **partly**: the harness value is preferred and T-10 re-checks at the write. The *which reading is served* question is open | engine item "effort gate" below |
| 4 | week window and calendar | **open**: `cmd_week` still uses `days[-5:]`; no calendar endpoint | `tools/trading_day.py` `cmd_week` |
| 5 | B-16 (a leg promoted from `held`) | **partly verified**: on DT's fill the take-profit leg promoted to `new` with `gtc`. The stop stayed `held`, its normal working state | 2026-09-23 broker read, `c2cd559` |
| 6 | leg-safety of `cancel_unfilled_entries()` live | **still unproven**: it has never run with a position open | F-3: it cancelled nothing, vacuously |
| 7 | D-17 fractional probe | **resolved**: both halves HTTP 422, the $75 ceiling stands | `071a501` |
| 8 | pullback entry vs chase | **evidence changed**: six years say chase beats retest (retest won only in 2026). Live path still rests at the level | `docs/16-entry-study.md`, `803a6b1`. **Decision for recalcitrantmaus** |
| 9 | D-24 target treatment | engine item below | |
| 10 | short entry bypasses the gate (M-7) | engine item below | |
| 11 | "carry only what you'd put on fresh" | **precedent, not rule**: now in the pre-close prompt, not in code | |
| F-1 | open refused by the classifier | **fixed and proven** for the close path; an open that submits is still unproven | F-2, F-3, `d2ea9f9` |
| relay | reports never arrived | **root-caused**: `fire_trigger` spawns a new session | `2026-09-26-rca-relay.md` |
| F-3 | three small bugs | **fixed** with regression tests | `a9f276f` |

### What the week actually proved and did not

Proved against reality:
- an engine-sized order reaching a fill (DT, 2026-09-23)
- B-15, fills recovered from the broker
- the pre-close entry cancel
- the one-command-per-call permission path, through a full close

Still unproven:
- the posture gate blocking a real order
- an empty plan binding against a scanner that disagrees
- trailing and scaling out
- any carry held overnight with a position on
- an open that submits under the new command form

### Recommendation on Monday 2026-09-28

Arm it, with the scheduled-post-back fix and the one-command-per-call prompts.
**Rehearse in a throwaway session only.** The first new thing Monday can prove
is an open that submits under the new form. recalcitrantmaus's decision.
