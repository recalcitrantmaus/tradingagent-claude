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
