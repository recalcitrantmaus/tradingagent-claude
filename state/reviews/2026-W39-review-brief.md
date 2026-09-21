# What a cleared reviewer should look at — written 2026-09-21, 16:15 ET

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
