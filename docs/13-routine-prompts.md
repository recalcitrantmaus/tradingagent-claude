# Routine prompts

Routine prompts are operational configuration. They live here so they are
versioned, reviewable and recoverable — a prompt that exists only in the
claude.ai UI is lost the moment someone edits it.

A Routine created in the web UI cannot be edited by an agent (`update_trigger`
refuses: "Agents can only update routines they created"). So these are written
here and pasted in by hand at
`https://claude.ai/code/routines/<trigger_id>`.

---

## Phase 2 Testing: Monday Session Open

- **Trigger:** `trig_0182kaYeNpaEfFjai8sRRfW7`
- **Fires:** 2026-09-21 13:45 UTC (09:45 ET / 06:45 PT), one-shot
- **Model:** `claude-opus-5` — deliberately, so the dev pass is Opus-cleared
- **Session:** fresh per firing (`persist_session: false`)
- **Notifications:** push

**Before it runs, confirm in the UI that the repository
`recalcitrantmaus/tradingagent-claude` is attached.** A fresh-session-on-fire
inherits the *environment*, not the repository — that is bug B-07, and it is
what cost us Wednesday 2026-09-16. The prompt below fails loudly rather than
silently if the repo is missing, but it cannot supply one.

Paste everything between the markers:

<!-- ---8<--- BEGIN ROUTINE PROMPT ---8<--- -->
Phase 2, Monday 2026-09-21, 09:45 ET. Full session-open set, then a dev pass. You are on Opus 5 for this firing deliberately: recalcitrantmaus wants one complete trading set AND the two control fixes landed in the same cycle.

Read CLAUDE.md first. The rule that outranks everything: the model decides what to trade, code decides whether it is allowed. If RiskOfficer rejects an order, record the rejection and move on — never reshape the order until it passes.

=== 0. ENVIRONMENT — stop here if any of this fails ===

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If that fails you have NO REPOSITORY. That is bug B-07 and it cost us Wednesday 2026-09-16. Do not try to clone. Report it as the finding and stop.

git pull origin claude/trading-agent-robinhood-cb9xo7

MODEL: the environment sets TRADING_AGENT_MODEL=claude-sonnet-5 at the ENVIRONMENT level, so tools.model_check will claim Sonnet whatever you are. This firing is configured for Opus 5. Verify your real model from the session record (get_session, with session_id omitted — read session_context.model and external_metadata.last_served_model), then pass it explicitly:
  python3 -m tools.model_check <task> --model <the model you verified>
If the session record disagrees with claude-opus-5, say so and do NOT do the dev pass in section 3 — rule-adjacent work needs Opus at xhigh.

python3 -m tools.preflight_phase2     # non-zero means DO NOT TRADE

A 09:35 ET smoke test should already have run and left the account flat. Confirm it did: the account must be flat with no resting orders before you open risk.

=== 1. THE TRADING SET — this comes first, the market does not wait ===

python3 -m tools.trading_day open     # non-zero means DO NOT TRADE

Then the skills, in order: premarket-brief, news-intel, trade-plan.
- Every factual claim carries a source URL. Never invent a price or a citation. If data could not be retrieved, say "unavailable" and downgrade posture.
- tools.screen must run before you conclude there is no setup, and the plan must state the denominator it screened. "No setup" computed over six tickers is not a market condition (bug B-10).
- An empty plan is binding and means trade nothing. The mechanical scanner is NOT consulted after one.

Then execution:
  python3 -m tools.paper_session --submit

THIS IS THE FIRST REAL SUBMIT ATTEMPT OF PHASE 2. Whatever happens, report it exactly. If a permission prompt blocks it, that is the finding — say so plainly and do not work around it. If an order is submitted, report the broker's response, whether it filled, and at what price against the proposal.

Known-unproven paths you may get to exercise for the first time — call out any that actually run: the posture gate blocking a real order; the binding empty plan on --submit rather than --dry-run; an engine-sized order reaching a fill.

Do not open crypto. The broker will not attach a stop to it (422 on bracket and oto), so "no stop, no trade" already forbids it — see D-21.

=== 2. ON THE READ-BACK OF R (context you need before the plan) ===

Do not change min_expected_r. It is 1.5 and it stays 1.5 this session.

Be aware of D-24, still OPEN: the mechanical target (entry + 3*ATR) is >=2.0R by construction and can never fail the gate, while a free-form structural target produced 0.3-0.5R and zero trades in three sessions. On Friday all three refusals ROSE and two traded straight through the specific level named as the reason they could not reach target. If you refuse a candidate on structural R, write down the exact level and why, so the refusal can be checked against the tape later. That record is the only reason Friday's error was findable.

=== 3. DEV PASS — only after the trading set is complete and pushed ===

Two control defects, both found 2026-09-18, both documented in docs/04-lessons.md. Each needs a test and a lessons entry per CLAUDE.md.

(a) RECONCILIATION CANNOT SEE CASH DRIFT. tools/trading_day.py reconcile() compares position symbols and trading_blocked, then adopts broker equity wholesale. Worse: ledger["cash"] is written NOWHERE after init — it is stuck at 300.0 from state.EMPTY, and reconcile() only reads it in the offline branch, which would therefore report $300.00 forever.

Fix by checking CASH, not equity — equity moves legitimately every second, cash only moves when something happens:
  expected_cash = ledger["broker_cash"] + cash effect of fills recorded since
  drift > $0.005            -> note it, record it, surface it in the close
  drift > max($1, 0.5% eq)  -> ok = False, which stops the day

Carry it day to day: write ledger["broker_cash"] and ledger["broker_equity"] at every open AND close, and append {date, expected, actual, drift} to ledger["reconcile_drift"]. Make the offline branch report the last broker-observed figure with its date so a stale number looks stale.

Tests: clean match; unexplained drift noted; drift explained by a recorded fill stays clean; drift above the halt threshold returns ok=False.

(b) THE MODEL GATE READS AN ENVIRONMENT CONSTANT. engine/model_policy.current_model() reads TRADING_AGENT_MODEL, which is environment-wide, so every session in this environment reports the same model regardless of what it runs. Today it fails closed, which is luck rather than design: set that variable to an opus id and every Sonnet session would claim Opus and pass the one gate meant to stop that. Claude Code exports NO model variable, so there is no better source available to a Python process — the fix is honesty about provenance, not a better guess. Make model_check report where its value came from, and treat an environment-sourced value as UNVERIFIED for blocking tasks unless --model was passed explicitly.

Both must pass:
  python3 -m unittest discover -s tests
  python3 -m sim.run_suite --seeds 300

Commit each separately with its lessons entry, and push.

=== 4. REPORT ===

Lead with whichever is true and easiest to skip: an order actually submitted, or a permission denial. Then: equity and day P&L; what the screen found and out of how many names; what was proposed, approved, rejected and by which gate; anything held and whether it is protected; both dev fixes with test counts; and what is still unproven in a live path.

Do not run the weekly review. Do not promote, change or delete any trading rule beyond the two fixes above — those are control fixes, not strategy changes. Commit and push everything, including state/. The container is reclaimed after the session, so anything not pushed did not happen.

<!-- ---8<--- END ROUTINE PROMPT ---8<--- -->

---

## AMENDMENT to the Session Open prompt — corrected universe

`data/universe.json` was built 2026-09-17 and is stale by Monday. More
importantly, `docs/15-point-in-time-study.md` established that the `size: 150`
liquidity cap is **load-bearing, not a convenience** — the same strategy across
all 1,563 eligible names is negative on every arm. So the universe must be
rebuilt fresh, and the cap must stay.

Insert this into section 1 of the Session Open prompt, immediately before the
line beginning "Then the skills, in order":

<!-- ---8<--- BEGIN OPEN AMENDMENT ---8<--- -->
REBUILD THE UNIVERSE FIRST. data/universe.json is from 2026-09-17 and
eligibility moves daily:

  python3 -m tools.screen --build-universe

Keep the size cap at 150. Do not widen it. docs/15-point-in-time-study.md
measured the same strategy across all 1,563 eligible names and every arm was
negative; restricting to the 150 most liquid names per day is what brings it
back to roughly break-even. The cap is a control, not a performance setting.
Report how many names the rebuild produced and how many changed versus the
committed file, then commit data/universe.json before screening.
<!-- ---8<--- END OPEN AMENDMENT ---8<--- -->

---

## Monday midday management — 12:00 ET (16:00 UTC)

One-shot, model Opus 5, repository attached, push notification on.

<!-- ---8<--- BEGIN MIDDAY PROMPT ---8<--- -->
Midday management, Monday 2026-09-21, 12:00 ET. This session MANAGES existing
risk. It does not open new risk, for any reason.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
If that fails, STOP and report — you have no repository.

git pull origin claude/trading-agent-robinhood-cb9xo7
If state/ledger.json is missing or tagged "reborn", STOP and report. That is
the finding of the day.

1. RECONCILE AND CHECK PROTECTION.

  python3 -m tools.trading_day open
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); ac=a.account(); print('equity',ac['equity'],'cash',ac['cash'],'daytrades',ac['daytrade_count']); print('positions',a.positions()); print('orders',[(o['symbol'],o['type'],o['status']) for o in a.open_orders()]); print('UNPROTECTED:',a.positions_without_stops())"

UNPROTECTED must be []. Anything listed is unmanaged risk: fix it or flatten
it before doing anything else, and say so loudly at the top of your report.

2. THIS MORNING WAS THE FIRST LIVE SUBMIT OF PHASE 2. Verify what it actually
did — these paths have never run against a real fill:

 - Did paper_session --submit place an order, or was it refused? If refused,
   quote the refusal verbatim.
 - If anything FILLED: read state/fills.jsonl. The row must carry the BROKER's
   filled_avg_price and filled_qty, not the proposed price. Compare against the
   plan and report the realised slippage. A row written at the proposed price
   is bug B-15 regressing.
 - If anything did NOT fill: state/fills.jsonl must contain NO row for it, and
   ledger["working_orders"] must carry it. An unfilled order recorded as a fill
   corrupts the FIFO pairing and the option-unlock gate.
 - For any filled position, confirm the bracket legs are live and their
   time_in_force is gtc. Under "day" the stop is cancelled at 16:00 with the
   position still open — that is bug B-16, fixed 2026-09-18, and this is the
   first live position since.

3. MANAGE, under the rules as they exist TODAY.

Targets are still mandatory (require_target=True, min_expected_r=1.5). Do not
act as though the no-target change has been made — it has not.

 - Scale out at the first target per config, then move that stop to breakeven.
 - Trail the remainder past +1R by 1.5 ATR.
 - Exit a thesis that has broken, whatever the P&L.
 - NEVER widen a stop. NEVER average down. NEVER add to a loser.

4. OBSERVE FOR THE PENDING TARGET DECISION — record, do not act.

docs/15-point-in-time-study.md is unresolved: no-target ranked best of the
arms tested but is not statistically significant after correcting for
survivorship. For each open position, write down where the take-profit sits
and whether the move looks capped by it. That observation is the only live
evidence we will have when the decision is made. Do NOT remove or widen a
target to test the hypothesis.

5. DAY-TRADE BUDGET. Closing a position opened this morning is a day trade;
the limit is 3 in 5 business days. Check the count. If the budget is the
binding constraint on an exit you would otherwise take, hold and flag it
loudly — that is a structural constraint worth surfacing, not a detail.

6. NO NEW ENTRIES. None.

7. Commit and push state/.

Report, short: equity and day P&L; what filled and at what price against the
plan; whether every position is protected; what you managed and why; the
target-cap observation; day-trade budget remaining; and any of the Phase 2
firsts in step 2 that ran for the first time.
<!-- ---8<--- END MIDDAY PROMPT ---8<--- -->

---

## Monday pre-close management — 15:30 ET (19:30 UTC)

One-shot, model Opus 5, repository attached, push notification on.

<!-- ---8<--- BEGIN PRE-CLOSE PROMPT ---8<--- -->
Pre-close management, Monday 2026-09-21, 15:30 ET — 30 minutes before the
bell. This session decides what is carried overnight. It does not open new
risk.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
git pull origin claude/trading-agent-robinhood-cb9xo7

1. RECONCILE AND VERIFY PROTECTION.

  python3 -m tools.trading_day open
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print('UNPROTECTED:', a.positions_without_stops()); print(a.positions()); print([(o['symbol'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders()])"

WEEK_HALT or LOCKED means flatten at the next orderly opportunity.

2. THE OVERNIGHT DECISION, explicitly, per position.

A stop is a fill instruction, not a price guarantee, and it does not hold
through a gap. For each name: state whether you are carrying it and why, and
price the gap risk at roughly twice the stop distance. Carry only what you
would put on fresh right now. "It is already on" is not a reason, and neither
is avoiding a day trade.

3. VERIFY THE GTC FIX ON A REAL POSITION — first opportunity since it landed.

Every protective leg must show time_in_force = gtc. If any leg shows "day",
the stop will be cancelled at 16:00 with the position still open and the
account will be naked overnight. That is a flatten-or-fix event, not a note:
fix it or close the position before the bell, and say so at the top.

4. Final management pass: scale out at a hit target and move that stop to
breakeven, trail past +1R by 1.5 ATR, exit a broken thesis. Never widen a stop.

5. DAY-TRADE BUDGET — check the count before any exit of a position opened
today. Flag loudly if the budget is what forced a carry.

6. NO NEW ENTRIES.

7. Commit and push state/.

Report: what you are carrying and why, per name; what you closed; day-trade
budget remaining; total overnight gap risk in dollars and as a percentage of
equity; and explicit confirmation that every leg is gtc.
<!-- ---8<--- END PRE-CLOSE PROMPT ---8<--- -->

---

## Monday session close — 16:05 ET (20:05 UTC)

One-shot, model Opus 5, repository attached, push notification on.

<!-- ---8<--- BEGIN CLOSE PROMPT ---8<--- -->
Session close, Monday 2026-09-21, 16:05 ET. The market has just closed.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; echo "$REPO"; cd "$REPO"
git pull origin claude/trading-agent-robinhood-cb9xo7

1. python3 -m tools.trading_day close

This now cancels resting ENTRY orders and re-reads positions_without_stops()
afterwards. Both are new as of 2026-09-18 and neither has run live. Confirm
from its output:
 - which resting entries it cancelled, if any
 - that it did NOT cancel any protective leg. A filled position must still
   have its stop. cancel_all() would have stripped them; cancel_unfilled_
   entries() must not. If a position lost its stop, that is the finding of the
   day — restore it or flatten, immediately, and lead the report with it.

2. VERIFY PROTECTION INTO THE NIGHT.

  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print('UNPROTECTED:', a.positions_without_stops()); print([(o['symbol'],o['type'],o['time_in_force'],o['status']) for o in a.open_orders()])"

Must print []. Every leg must read gtc.

3. MANUAL CASH-DRIFT CHECK — the automated one does not exist yet.

reconcile() compares position symbols and adopts broker equity wholesale; it
cannot see cash moving without a position change (the fix lands Tuesday, see
docs/04-lessons.md 2026-09-18). Do it by hand tonight:

  expected_cash = yesterday's broker cash
                + proceeds of everything sold today
                - cost of everything bought today

Compare against the broker's cash. Yesterday's close was $299.99 with the
account flat. Any difference you cannot attribute to a recorded fill is the
finding, however small — a cent and a dollar have the same causes. Write the
number into the report either way, including when it is zero.

4. trade-journal for every position closed today: one entry each, with the
original thesis and its source URL, what actually happened, and whether the
outcome came from process or luck. Flag loudly any winning trade taken
off-plan — it got paid for a mistake and teaches the wrong lesson.

5. python3 -m tools.review  and  python3 -m tools.trading_day week

6. DO NOT run the weekly review and do not promote, change or delete any
trading rule. Check: python3 -m tools.model_check weekly-review --model <the
model you verified from the session record> — and respect the result. Write up
what a reviewer should look at and leave the judgement to a cleared session.

7. Commit and push everything in state/ — ledger, fills, brief, plan, news,
report, journal. The container is reclaimed after the session; anything not
pushed did not happen.

Report, leading with whichever is true:
 - equity, day P&L, and the honest gap to the +5% weekly hurdle. It is a
   hurdle rate, not a quota, and it is never closed with leverage.
 - WHAT FIRED FOR THE FIRST TIME. Monday was the first live submit attempt of
   Phase 2. Name explicitly which of these ran against reality: an order
   submitted through the permission grant; an engine-sized order reaching a
   fill; fill_record writing the broker's price; ledger["working_orders"]
   carrying an unfilled order; cancel_unfilled_entries leaving legs alone; a
   GTC leg surviving into the night. Anything that did NOT run is still
   unproven and must be said so.
 - trades opened and closed, and the measured expectancy. One day is noise.
   Say so.
 - costs against realised gains.
 - the cash-drift number from step 3.
 - every guardrail that fired, and any that should have fired and did not.
 - what is carried overnight, the gap risk on it, and that it is protected.
<!-- ---8<--- END CLOSE PROMPT ---8<--- -->

---

## Monday wrap for recalcitrantmaus — 16:35 ET (20:35 UTC), optional

Short, human-facing. Skip it if you would rather just read the close report.

<!-- ---8<--- BEGIN WRAP PROMPT ---8<--- -->
Monday day-one wrap for recalcitrantmaus, 16:35 ET. The 16:05 close session should have
finished and pushed. Keep this SHORT — about six lines.

git pull, then verify against the broker rather than trusting the report:
  python3 -c "from adapters.alpaca import AlpacaAdapter; a=AlpacaAdapter(); print(a.account()); print(a.positions()); print('UNPROTECTED:', a.positions_without_stops())"

Then read state/reports/2026-09-21*.md and tell recalcitrantmaus:
 - equity and day P&L
 - whether the submit path actually ran, and what happened
 - what is held overnight and whether it is protected
 - which Phase 2 firsts are now proven and which are still unproven
 - the two Tuesday items: the reconciliation cash-drift fix and the
   model_check provenance fix
 - anything that needs her decision before Tuesday

Say loudly if anything is unprotected overnight, or if the day's finding
contradicts docs/15-point-in-time-study.md. Point her at the close session for
detail. Do not make code changes in this firing.
<!-- ---8<--- END WRAP PROMPT ---8<--- -->
