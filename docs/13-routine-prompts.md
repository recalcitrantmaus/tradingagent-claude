# Routine prompts — Monday 2026-09-21

Routine prompts are operational configuration. They live here so they are
versioned, reviewable and recoverable — a prompt that exists only in the
claude.ai UI is lost the moment someone edits it.

A Routine created in the web UI **cannot be edited by an agent**
(`update_trigger` refuses: "Agents can only update routines they created").
So these are pasted in by hand at
`https://claude.ai/code/routines/` + the trigger id.

**Never put `<angle brackets>` inside a prompt body.** The Routines editor
strips them as HTML tags, silently. On 2026-09-20 that turned
`model_check <task> --model <verified model>` into
`model_check  --model` in two live Routines — a command that exits on an
argparse error. Use `CAPITALISED_PLACEHOLDERS` instead. The editor also drops
leading list markers (`1.`, `-`) and inserts blank lines; that is cosmetic and
does not need fixing, but the angle brackets do.

## The day

| ET | UTC | firing | trigger |
|---|---|---|---|
| 09:35 | 13:35 | smoke test — order path + permission grant | `trig_016AFZC5T5FPDd9QhMo3EJtC` |
| 09:45 | 13:45 | session open | `trig_0182kaYeNpaEfFjai8sRRfW7` |
| 12:00 | 16:00 | midday management | *to create* |
| 15:30 | 19:30 | pre-close, carry decision | *to create* |
| 16:05 | 20:05 | session close | *to create* |
| 16:35 | 20:35 | wrap for recalcitrantmaus (optional) | *to create* |

All fresh-session-per-fire, **repository attached**, model **Opus 5**, push
notifications on.

Two standing cautions for every one of them:

- **A fresh session inherits the environment, not the repository.** That is
  bug B-07 and it cost us Wednesday 2026-09-16. Every prompt below re-derives
  the repo path first and stops loudly if it is absent; none of them can
  supply one. Confirm the attachment in the UI.
- **`TRADING_AGENT_MODEL` is an environment-level default** reading
  `claude-sonnet-5`, and it is wrong for these firings. As of 2026-09-20
  `model_check` refuses any *blocking* task on an unverified model and tells
  you how to fix it; pass `--model` after reading the session record.

## State as of the last commit before Monday

Equity **$299.99**, flat, no open orders, nothing unprotected, 0 day trades.
Cash anchor recorded at $299.99 — Monday's open will compare against it.

---

## 1. Session open — 09:45 ET (13:45 UTC)

Replaces the earlier draft in full. The dev pass is gone: both control fixes
landed 2026-09-20.

<!-- ---8<--- BEGIN OPEN ---8<--- -->
Phase 2, Monday 2026-09-21, 09:45 ET. Full session-open set. This is the first
trading day running on the corrected controls.

Read CLAUDE.md first. The rule that outranks everything: the model decides
what to trade, code decides whether it is allowed. If RiskOfficer rejects an
order, record the rejection and move on — never reshape the order until it
passes.

=== 0. ENVIRONMENT — stop here if any of this fails ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If that fails you have NO REPOSITORY (bug B-07, which cost us Wednesday
2026-09-16). Do not try to clone. Report it as the finding and stop.

git pull origin claude/trading-agent-robinhood-cb9xo7

MODEL: verify from the session record (get_session with session_id omitted —
read session_context.model and external_metadata.last_served_model). The
environment variable says claude-sonnet-5 and is wrong for this firing; as of
2026-09-20 model_check refuses blocking tasks on an unverified model. Pass
your verified model when you need one:
  python3 -m tools.model_check TASK_NAME --model THE_MODEL_YOU_VERIFIED
e.g.  python3 -m tools.model_check execution --model claude-opus-5

python3 -m tools.preflight_phase2     # non-zero means DO NOT TRADE

The 09:35 smoke test should have run and left the account flat. Confirm: flat,
no resting orders, before you open any risk.

=== 1. REBUILD THE UNIVERSE ===

  python3 -m tools.screen --build-universe

data/universe.json is from 2026-09-17 and eligibility moves daily. KEEP THE
SIZE CAP AT 150 — do not widen it. docs/15-point-in-time-study.md measured
this strategy across all 1,563 eligible names and every arm was negative;
restricting to the 150 most liquid per day is what brings it back to roughly
break-even. The cap is a control, not a performance setting.

Report how many names it produced and how many changed against the committed
file. Commit data/universe.json before screening.

=== 2. OPEN THE DAY ===

  python3 -m tools.trading_day open     # non-zero means DO NOT TRADE

This now carries a CASH-DRIFT check, new on 2026-09-20 and running against a
real anchor for the first time. The anchor is $299.99 from 2026-09-20. Read
its output:
 - silence means broker cash matched expectation. Say so explicitly.
 - a "CASH DRIFT" note means broker cash moved in a way the fill log does not
   explain. Report the number whatever its size — a cent and a dollar have the
   same causes.
 - "DO NOT TRADE" means the drift exceeded max($1, 0.5% of equity). Stop, and
   report.

=== 3. THE TRADING SET ===

Then the skills, in order: premarket-brief, news-intel, trade-plan.
 - Every factual claim carries a source URL. Never invent a price or a
   citation. If data could not be retrieved, say "unavailable" and downgrade
   posture.
 - tools.screen must run before you conclude there is no setup, and the plan
   must state the denominator it screened.
 - An empty plan is binding and means trade nothing. The mechanical scanner is
   NOT consulted after one.

Then execution:
  python3 -m tools.paper_session --submit

THIS IS THE FIRST REAL SUBMIT ATTEMPT OF PHASE 2. Report exactly what happens.
If a permission prompt blocks it, that is the finding — say so plainly and do
not work around it. If an order is submitted, report the broker's response,
whether it filled, and at what price against the proposal.

Call out any of these that runs against reality for the first time: the
posture gate blocking a real order; the binding empty plan on --submit rather
than --dry-run; an engine-sized order reaching a fill; fill_record writing the
broker's price; ledger["working_orders"] carrying an unfilled order.

Do not open crypto. The broker will not attach a stop to it (422 on bracket
and oto), so "no stop, no trade" already forbids it — see D-21.

=== 4. ON TARGETS — context, not instruction ===

Targets are still MANDATORY (require_target=True, min_expected_r=1.5). Do not
act as though the no-target change has been made; it has not, and it is not
yours to make today.

D-24 is open. docs/15-point-in-time-study.md found no-target ranked best of
the arms tested but NOT statistically significant once survivorship was
removed, and every arm negative in Q3 2026. If you refuse a candidate on
structural reward-to-risk, write down the exact level and why, so the refusal
can be checked against the tape later. That record is the only reason
Friday's error was findable.

=== 5. REPORT AND PUSH ===

Commit and push everything, including state/ and data/universe.json. The
container is reclaimed after the session; anything not pushed did not happen.

Lead with whichever is true and easiest to skip: an order actually submitted,
or a permission denial. Then: the universe rebuild; the cash-drift line;
equity and day P&L; what the screen found and out of how many names; what was
proposed, approved and rejected, and by which gate; anything held and whether
it is protected.

Do not run the weekly review. Do not promote, change or delete any rule.
<!-- ---8<--- END OPEN ---8<--- -->

---

## 2. Midday management — 12:00 ET (16:00 UTC)

<!-- ---8<--- BEGIN MIDDAY ---8<--- -->
Midday management, Monday 2026-09-21, 12:00 ET. This session MANAGES existing
risk. It does not open new risk, for any reason.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If that fails, STOP and report — you have no repository.

git pull origin claude/trading-agent-robinhood-cb9xo7
If state/ledger.json is missing or tagged "reborn", STOP and report. That is
the finding of the day.

1. RECONCILE AND CHECK PROTECTION.

  python3 -m tools.trading_day open
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash'],'daytrades',ac['daytrade_count']); print('positions',a.positions()); print('orders',[(o['symbol'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders()]); print('UNPROTECTED:',a.positions_without_stops())"

UNPROTECTED must be []. Anything listed is unmanaged risk: fix or flatten it
before anything else, and lead your report with it.

Report the cash-drift line from trading_day open, including when it is clean.
If an order filled this morning the drift should be EXPLAINED by that fill and
the check should stay quiet; an unexplained drift alongside a fill means the
fill log and the broker disagree, which matters more than the amount.

2. VERIFY THIS MORNING'S SUBMIT — these paths have never run against a real
fill.

 - Did paper_session --submit place an order, or was it refused? Quote any
   refusal verbatim.
 - If anything FILLED: read state/fills.jsonl. The row must carry the BROKER's
   filled_avg_price and filled_qty, not the proposed price. Report realised
   slippage against the plan. A row at the proposed price is bug B-15
   regressing.
 - If anything did NOT fill: fills.jsonl must contain NO row for it, and
   ledger["working_orders"] must carry it.
 - For any filled position, confirm the bracket legs are live and their
   time_in_force is gtc. Under "day" the stop is cancelled at 16:00 with the
   position still open — bug B-16, fixed 2026-09-18, first live position since.

3. MANAGE, under the rules as they exist today. Targets are mandatory; there
is no time stop.

 - Scale out at the first target per config, then move that stop to breakeven.
 - Trail the remainder past +1R by 1.5 ATR.
 - Exit a thesis that has broken, whatever the P&L.
 - NEVER widen a stop. NEVER average down. NEVER add to a loser.

4. OBSERVE FOR THE PENDING TARGET DECISION — record, do not act. For each open
position write down where the take-profit sits and whether the move looks
capped by it. Do NOT remove or widen a target to test the hypothesis.

5. DAY-TRADE BUDGET. Closing a position opened this morning is a day trade;
the limit is 3 in 5 business days. If the budget is the binding constraint on
an exit you would otherwise take, hold and flag it loudly.

6. NO NEW ENTRIES. None.

7. Commit and push state/.

Report, short: equity and day P&L; the cash-drift line; what filled and at
what price against the plan; whether every position is protected and every leg
is gtc; what you managed and why; the target-cap observation; day-trade budget
remaining.
<!-- ---8<--- END MIDDAY ---8<--- -->

---

## 3. Pre-close and carry decision — 15:30 ET (19:30 UTC)

<!-- ---8<--- BEGIN PRE-CLOSE ---8<--- -->
Pre-close management, Monday 2026-09-21, 15:30 ET — 30 minutes before the
bell. This session decides what is carried overnight. It does not open new
risk.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
git pull origin claude/trading-agent-robinhood-cb9xo7

1. RECONCILE AND VERIFY PROTECTION.

  python3 -m tools.trading_day open
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print('UNPROTECTED:', a.positions_without_stops()); print(a.positions()); print([(o['symbol'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders()])"

WEEK_HALT or LOCKED means flatten at the next orderly opportunity. Report the
cash-drift line.

2. VERIFY THE GTC FIX ON A REAL POSITION — first opportunity since it landed.

Every protective leg must read time_in_force = gtc. If any leg reads "day",
the stop is cancelled at 16:00 with the position still open and the account
goes naked overnight. That is a flatten-or-fix event, not a note: fix it or
close the position before the bell, and lead your report with it.

3. THE OVERNIGHT DECISION, explicitly, per position.

A stop is a fill instruction, not a price guarantee, and it does not hold
through a gap. For each name: state whether you are carrying it and why, and
price the gap risk at roughly twice the stop distance. Carry only what you
would put on fresh right now. "It is already on" is not a reason, and neither
is avoiding a day trade.

4. Final management pass: scale out at a hit target and move that stop to
breakeven, trail past +1R by 1.5 ATR, exit a broken thesis. Never widen a stop.

5. DAY-TRADE BUDGET — check the count before exiting anything opened today.
Flag loudly if the budget is what forced a carry.

6. NO NEW ENTRIES.

7. Commit and push state/.

Report: what you are carrying and why, per name; what you closed; day-trade
budget remaining; total overnight gap risk in dollars and as a percentage of
equity; and explicit confirmation that every leg is gtc.
<!-- ---8<--- END PRE-CLOSE ---8<--- -->

---

## 4. Session close — 16:05 ET (20:05 UTC)

<!-- ---8<--- BEGIN CLOSE ---8<--- -->
Session close, Monday 2026-09-21, 16:05 ET. The market has just closed.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
git pull origin claude/trading-agent-robinhood-cb9xo7

1. python3 -m tools.trading_day close

Three things in its output are new and have never run live. Confirm each:

 a. CASH DRIFT. The check compares broker cash against the anchor plus every
    recorded fill since it. Report the number whatever it is, including zero.
    An unexplained drift is the finding of the day at any size.
 b. CANCELLED ENTRIES. It cancels resting ENTRY orders so an unfilled entry
    does not fire tomorrow on a gap against a stale thesis. Report which, if
    any.
 c. IT MUST NOT HAVE CANCELLED A PROTECTIVE LEG. A filled position must still
    have its stop. cancel_all() would have stripped them; cancel_unfilled_
    entries() must not. If a position lost its stop, restore it or flatten
    immediately and lead the report with it.

2. VERIFY PROTECTION INTO THE NIGHT.

  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print('UNPROTECTED:', a.positions_without_stops()); print([(o['symbol'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders()])"

Must print []. Every leg must read gtc.

3. trade-journal for every position closed today: one entry each, with the
original thesis and its source URL, what actually happened, and whether the
outcome came from process or luck. Flag loudly any winning trade taken
off-plan — it got paid for a mistake and teaches the wrong lesson.

4. python3 -m tools.review  and  python3 -m tools.trading_day week

5. DO NOT run the weekly review and do not promote, change or delete any
trading rule. Check first:
  python3 -m tools.model_check weekly-review --model THE_MODEL_YOU_VERIFIED
(substitute the model you read from the session record, e.g.
 claude-opus-5 — do NOT leave --model empty, argparse will error)
and respect the result. Write up what a reviewer should look at and leave the
judgement to a cleared session.

6. Commit and push everything in state/ — ledger, fills, brief, plan, news,
report, journal. The container is reclaimed; anything not pushed did not
happen.

Report, leading with whichever is true:
 - equity, day P&L, and the honest gap to the +5% weekly hurdle. It is a
   hurdle rate, not a quota, and it is never closed with leverage.
 - WHAT FIRED FOR THE FIRST TIME. Monday was the first live submit attempt of
   Phase 2 and the first day on the corrected controls. Name explicitly which
   of these ran against reality: an order submitted through the permission
   grant; an engine-sized order reaching a fill; fill_record writing the
   broker's price; ledger["working_orders"] carrying an unfilled order;
   cancel_unfilled_entries leaving legs alone; a GTC leg surviving into the
   night; the cash-drift check finding something. ANYTHING THAT DID NOT RUN IS
   STILL UNPROVEN AND MUST BE SAID SO — a quiet day must not read as success.
 - trades opened and closed, and measured expectancy. One day is noise. Say so.
 - costs against realised gains.
 - every guardrail that fired, and any that should have fired and did not.
 - what is carried overnight, the gap risk on it, and that it is protected.
<!-- ---8<--- END CLOSE ---8<--- -->

---

## 5. Wrap for recalcitrantmaus — 16:35 ET (20:35 UTC), optional

<!-- ---8<--- BEGIN WRAP ---8<--- -->
Monday wrap for recalcitrantmaus, 16:35 ET. The 16:05 close should have finished and
pushed. Keep this SHORT — about six lines.

git pull, then verify against the broker rather than trusting the report:
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print(a.account()); print(a.positions()); print('UNPROTECTED:', a.positions_without_stops())"

Read state/reports/2026-09-21*.md and tell recalcitrantmaus:
 - equity and day P&L
 - whether the submit path actually ran, and what happened
 - what is held overnight and whether it is protected
 - which Phase 2 firsts are now proven, and which are still unproven
 - whether the day's evidence agrees or disagrees with
   docs/15-point-in-time-study.md
 - anything needing her decision before Tuesday — D-24 (the no-target and
   time-stop change) is the open one

Say loudly if anything is unprotected overnight. Point her at the close
session for detail. Do not make code changes in this firing.
<!-- ---8<--- END WRAP ---8<--- -->
