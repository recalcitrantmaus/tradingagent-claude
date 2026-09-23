#!/usr/bin/env python3
"""Generate docs/design-documentation.xlsx — decisions, bugs, systems.

The data lives here rather than in the workbook so that it is diffable, review-
able in a pull request, and regenerable after the container is reclaimed. The
.xlsx is a build artifact of this file.

    pip install openpyxl
    python3 -m tools.design_doc

Every row is traceable: design decisions cite the file that enforces them and
the lessons entry that justified them; bugs cite the commit that fixed them.
Dates are taken from `git log`, not from memory.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design-documentation.xlsx"

# --------------------------------------------------------------------------
# Sheet 1 — major design decisions
# --------------------------------------------------------------------------
DECISIONS_COLS = ["ID", "Date", "Area", "Decision", "Rationale",
                  "Evidence", "Enforced by", "Status"]
DECISIONS = [
 ("D-01", "2026-09-15", "Governance",
  "The model decides what to trade; code decides whether it is allowed",
  "An LLM that can reshape an order until it passes has no risk control at "
  "all. Separating proposal from permission makes the guardrail unreachable "
  "by reasoning.",
  "CLAUDE.md, the founding rule",
  "engine/risk.py RiskOfficer.evaluate", "Active"),
 ("D-02", "2026-09-15", "Sizing",
  "Risk per trade capped at 2% of equity; size is derived from the stop",
  "Size follows the stop, never the ambition. The binding constraint is "
  "reported on every rejection so the reason is legible.",
  "docs/05-sim-report.md Result 2",
  "engine/config.py max_risk_per_trade_pct", "Active"),
 ("D-03", "2026-09-15", "Exits",
  "Every entry supplies a stop before it is placed, attached atomically",
  "A filled entry whose stop is a follow-up call is an unmanaged position for "
  "as long as the second call takes. Brackets make it one operation.",
  "CLAUDE.md hard constraints",
  "adapters/alpaca.py submit(), order_class=bracket", "Active"),
 ("D-04", "2026-09-15", "Exits",
  "Never widen a stop; never average down; scale out, not in",
  "Both are the standard mechanisms by which a small account converts a "
  "survivable loss into a terminal one.",
  "docs/04-lessons.md 2026-09-15 (two entries)",
  "engine/risk.py, tests/test_risk.py", "Active"),
 ("D-05", "2026-09-15", "Instruments",
  "Options locked twice: below $1,500 equity AND until 30 closed trades at "
  ">= +0.10R measured expectancy",
  "Affordability is not a quality gate. Simulation found long-premium buying "
  "negative at EVERY capital level tested ($300-$10,000), so an equity floor "
  "alone would have unlocked a losing strategy at $1,500.",
  "docs/05-sim-report.md Results 7 and 8",
  "engine/config.py option_min_equity + option_requires_proven_edge", "Active"),
 ("D-06", "2026-09-15", "Circuit breakers",
  "-4% day halts the day, -8% week halts the week, -20% from peak flattens "
  "and locks for a human",
  "Escalating, monotonic, and the last one is not self-clearing. LOCKED "
  "requires RiskOfficer.unlock(authorization) with a human note.",
  "docs/05-sim-report.md",
  "engine/risk.py State machine", "Active"),
 ("D-07", "2026-09-15", "Target",
  "5%/week is a hurdle rate, not a quota; report the gap honestly and never "
  "close it with leverage",
  "The strategy that most directly pursued it locked the account in 100% of "
  "300 runs; optimizing for 'weeks hitting +5%' selects for strategies that "
  "ruin 94% of accounts.",
  "docs/04-lessons.md 2026-09-15, sim ablation arms",
  "Prose + the target_chaser_CONTROL simulation arm", "Active"),
 ("D-08", "2026-09-15", "Model routing",
  "Rule-changing tasks require Opus at xhigh and STOP on a downgrade; "
  "trading tasks warn and continue",
  "A bad execution turn costs one trade; a bad rule promoted into a SKILL.md "
  "costs every trade until someone notices. The asymmetry is the point.",
  "docs/06-model-strategy.md",
  "engine/model_policy.py, tools/model_check.py", "Active"),
 ("D-09", "2026-09-16", "Governance",
  "An empty plan is binding: it means trade nothing, and the mechanical "
  "scanner is not consulted",
  "`propose_from_plan(today) or propose_mechanical(...)` treated a deliberate "
  "refusal as having no opinion, because [] is falsy. A refusal to trade must "
  "be distinguishable from an absent opinion.",
  "docs/04-lessons.md 2026-09-16 rehearsal, defect 1",
  "tools/paper_session.py, `is None` not `or`", "Active"),
 ("D-10", "2026-09-16", "Governance",
  "The brief's posture is enforced in code, and parsing fails closed",
  "NO_TRADE and RISK_OFF appeared only inside a comment string; the binding "
  "posture was enforced by the model's own compliance.",
  "docs/04-lessons.md 2026-09-16 rehearsal, defect 2",
  "engine/posture.py limits_for()", "Active"),
 ("D-11", "2026-09-16", "State",
  "state/ is tracked in git; .gitignore carries only secrets",
  "Every Routine firing gets a fresh container and clone. With state/ ignored, "
  "a HALTED_DAY cleared itself overnight and peak_equity reset to $300, so the "
  "drawdown lock could never trigger.",
  "docs/04-lessons.md 2026-09-15 circuit breakers",
  ".gitignore + a comment forbidding the lines' return", "Active"),
 ("D-12", "2026-09-17", "Data",
  "Reachable is not usable: a 200 carrying a bot challenge is DEGRADED, and "
  "a DEGRADED source is unavailable",
  "stooq, Reuters, AP, MarketWatch, CNBC and The Block all answered and none "
  "served data. Five of six news sources were bot walls reported healthy.",
  "docs/04-lessons.md 2026-09-17 (three entries)",
  "tools/netcheck.py challenge markers + 403 handling", "Active"),
 ("D-13", "2026-09-17", "Data",
  "Prefer an outlet's RSS feed over its HTML page",
  "All seven RSS feeds returned 10-49 parsed items where the equivalent HTML "
  "pages returned challenges. Feeds are built for machines.",
  "docs/04-lessons.md 2026-09-17 source replacement",
  ".claude/skills/news-intel/SKILL.md", "Active"),
 ("D-14", "2026-09-17", "Data",
  "Identify the agent honestly in the User-Agent, with a contact address",
  "A Mozilla UA string was being gated by .gov WAFs. Government sources ask "
  "for identification and serve identified clients.",
  "docs/04-lessons.md 2026-09-17",
  "tools/netcheck.py user_agent(), TRADING_AGENT_CONTACT", "Active"),
 ("D-15", "2026-09-17", "Data",
  "A keyless fallback must never gate a trading day",
  "Yahoo rate-limits under load. As a hard preflight dependency it could "
  "cancel a session on which Alpaca was perfectly healthy.",
  "docs/04-lessons.md 2026-09-17",
  "tools/preflight_phase2.py: Alpaca gates, Yahoo cross-checks", "Active"),
 ("D-16", "2026-09-17", "Universe",
  "The tradeable universe is a committed artifact built by a tool, not a "
  "hand-typed list",
  "'No setup today' was being computed against six hardcoded tickers. That is "
  "not a market condition, it is a six-ticker list. The screen must state its "
  "denominator.",
  "docs/04-lessons.md 2026-09-17",
  "tools/screen.py + data/universe.json (150 symbols)", "Active"),
 ("D-17", "2026-09-17", "Sizing",
  "Whole-share sizing stands; fractional shares are not adopted",
  "MEASURED: Alpaca rejects fractional brackets (42210000, 'fractional orders "
  "must be simple orders'). Fractional would widen a $300 account's universe "
  "only by giving up the atomic stop.",
  "docs/04-lessons.md 2026-09-17 smoke test",
  "engine/risk.py qty = float(int(qty))", "Active"),
 ("D-18", "2026-09-18", "Reward/risk",
  "Expected R >= 1.5 is enforced in code; no target, no grade, no trade",
  "The rule had been in CLAUDE.md, the runbook and the trade-plan skill since "
  "day one and existed in none of them as code. evaluate() never read "
  "p.target. Three approved breakouts on 2026-09-12 were refused only by "
  "prose judgement.",
  "docs/04-lessons.md 2026-09-18",
  "engine/config.py min_expected_r, engine/risk.py", "Active"),
 ("D-19", "2026-09-18", "Execution",
  "Only actual fills are written to the fill log, at the broker's price and "
  "quantity",
  "Recording on submission put phantom entries at the head of the FIFO queue "
  "and accrued them toward the option-unlock gate.",
  "docs/04-lessons.md 2026-09-18",
  "tools/paper_session.py fill_record(), adapters await_fill()", "Active"),
 ("D-20", "2026-09-18", "Execution",
  "Brackets are GTC so the stop outlives the session; session-close cancels "
  "resting ENTRIES only",
  "MEASURED: legs inherit the parent's time_in_force. Under 'day' the stop "
  "was cancelled at 16:00 with the position still open. cancel_all() cannot "
  "be used for the cleanup — it would strip live legs off open positions.",
  "docs/04-lessons.md 2026-09-18",
  "adapters/base.py OrderTicket, cancel_unfilled_entries()", "Active"),
 ("D-21", "2026-09-18", "Instruments",
  "No crypto, on the existing 'no stop, no trade' rule",
  "MEASURED: Alpaca rejects bracket and OTO for crypto (42210000); the only "
  "accepted crypto order has zero protective legs. 24/7 trading makes a "
  "missing stop worse, not better, for an agent that wakes on a schedule.",
  "docs/04-lessons.md 2026-09-18",
  "No code change — D-03 already covers it", "Active"),
 ("D-25", "2026-09-18", "Testing",
  "Anything guarding real money against an external system needs at least one "
  "test that talks to that system",
  "Two controls written on 2026-09-18 tested green against stubs and both "
  "failed against the live paper broker. Both bugs were assumptions about the "
  "broker's response shape, which is the one thing a stub cannot falsify — a "
  "stub encodes the belief it is supposed to be testing.",
  "docs/04-lessons.md 2026-09-18; bugs B-19 and B-20",
  "tools/smoke_submit.py, and live probes before any execution change",
  "Active"),
 ("D-23", "2026-09-18", "Strategy",
  "Measure which of the three diagnoses is happening before adjusting any "
  "threshold because nothing is trading",
  "'The strategy finds nothing', 'the account cannot take what it finds' and "
  "'the plan refuses what it could take' produce an identical symptom — an "
  "empty plan — and have three different fixes. Measured: 533 signals in 60 "
  "sessions, 507 approved by the engine at $300, tradeable on 98% of days. "
  "The universe was never the constraint; the plan is.",
  "docs/04-lessons.md 2026-09-18; tools.screen --replay 60",
  "tools/screen.py replay(), which calls RiskOfficer.evaluate itself",
  "Active"),
 ("D-24", "2026-09-18", "Strategy",
  "UNRESOLVED: mechanical vs structural target. Deferred to weekly-review at "
  "Opus/xhigh",
  "close + 3*ATR is 2.0R by construction and can never fail the expected-R "
  "gate; a structural target produced 0.3-0.5R on all three of Friday's "
  "candidates and zero trades in three sessions. Both cannot govern. This "
  "decides what the strategy IS and is not a threshold to nudge on a quiet "
  "morning.",
  "docs/04-lessons.md 2026-09-18",
  "Nothing yet — deliberately open",
  "OPEN"),
 ("D-22", "2026-09-18", "Carry",
  "Positions are carried overnight by design, not flattened daily",
  "Target is entry + 3*ATR, a multi-day objective, and PDT allows only 3 day "
  "trades per 5 business days. Flattening daily is neither desirable nor "
  "available. The close prices the 1x and 2x gap cases explicitly.",
  "engine/config.py max_day_trades_per_5d; trading_day close",
  "tools/trading_day.py cmd_close overnight risk block", "Active"),
 ("D-26", "2026-09-22", "Data",
  "Levels and volatility come from the CONSOLIDATED tape; the live price "
  "comes from a real-time venue feed. Never one source for both.",
  "A single-venue feed carries a median 3.8% of consolidated volume. That "
  "leaves means correct — prices agree to the cent — and EXTREMA wrong, in "
  "one direction, arithmetically: a subset of prints cannot contain a higher "
  "high or a lower low than the whole. Highs, lows and ATR are the only "
  "statistics the bar series is used for, so the error was total and could "
  "never average out. But consolidated data is 15 minutes delayed here, so it "
  "cannot price an entry. The two requirements are irreconcilable in one "
  "source, so the code takes each from where it is right.",
  "docs/04-lessons.md 2026-09-22; bug B-21. ATR smaller in 59 of 59 names, "
  "20d high understated in 43/59, 1 phantom breakout in 59.",
  "adapters/alpaca.py bars(feed='sip') and last_trade(); "
  "tools/screen.py breakout_now() takes level and price separately",
  "Active"),
 ("D-27", "2026-09-22", "Data",
  "The universe is built only from COMPLETED sessions",
  "A partial bar makes a liquidity floor a function of the time of day: at "
  "09:50 a $1.5M threshold behaved like ~$30M/day. It also made the build "
  "irreproducible — the scan walks ~11,800 assets over minutes, so the floor "
  "moved mid-build and a name excluded at the start passed at the end. A "
  "screen that vetoes trades has to mean the same thing when someone re-reads "
  "the decision next week.",
  "docs/04-lessons.md 2026-09-22; bug B-22. Two consecutive builds now give "
  "identical symbols, volumes and session label.",
  "tools/screen.py build_universe() reads prevDailyBar", "Active"),
 ("D-28", "2026-09-22", "Governance",
  "A blocking task requires a recorded human authorization, and the system "
  "states plainly that this is ATTRIBUTABLE, not enforceable",
  "Nothing in-process can establish that a human is present: any check the "
  "process can read, the process can satisfy. Two attempts to detect one "
  "failed — an environment-wide flag that never bound, then a session-id "
  "binding that the same session disproved by being unattended at 14:20Z and "
  "attended at 15:45Z. Attendance is a property of the TURN, and env vars are "
  "snapshotted at session start. So the claim is recorded instead of tested, "
  "and what IS enforced is narrow and honest: no trivial string, and no "
  "verbatim reuse, so it cannot be baked into a Routine and fired on a "
  "schedule.",
  "docs/04-lessons.md 2026-09-22; bug B-23; state/authorizations.jsonl",
  "engine/model_policy.py authorization_ok() and check()", "Active"),
]

# --------------------------------------------------------------------------
# Sheet 2 — bugs
# --------------------------------------------------------------------------
# "Created" is when the defect entered the codebase (from git log), not when
# it was noticed. The gap between Created and Discovered is the number worth
# looking at: it is how long the system looked correct while being wrong.
BUGS_COLS = ["ID", "Category", "Severity", "Issue", "Resolution",
             "Created (introduced)", "Discovered", "Solved",
             "Days latent", "Fixed in", "Status"]
BUGS = [
 ("B-01", "Data path", "Critical",
  "AlpacaAdapter.bars() sent no `start`, so Alpaca defaulted it to today and "
  "returned exactly 1 bar for any limit. propose_mechanical needs 21 bars for "
  "an ATR, so it skipped every symbol and printed 'no proposals today' — a "
  "data outage rendered as a market opinion.",
  "bars() derives a window from the requested length, pages to the end, and "
  "returns the tail. Two tests pin both failure modes.",
  "2026-09-15 18:36", "2026-09-15 20:45", "2026-09-15 20:45",
  "0", "39026f2", "Closed"),
 ("B-02", "Data path", "Critical",
  "Follow-on from B-01: Alpaca's `limit` truncates from the START of the "
  "range. A 60-bar request over 120 days returned real, correct-length, "
  "month-stale data. Stops and sizes would have been priced off prices that "
  "no longer existed.",
  "Pagination to the end of the window, then tail. Verified against the live "
  "endpoint: SPY 757.42 vs Yahoo 757.44, inside the 50bps tolerance.",
  "2026-09-15 20:45", "2026-09-15 20:45", "2026-09-15 20:45",
  "0", "39026f2", "Closed"),
 ("B-03", "State", "Critical",
  ".gitignore excluded state/ledger.json and state/fills.jsonl. Every Routine "
  "firing gets a fresh container and clone, and state.load() recreates EMPTY "
  "defaults. A day or week halt cleared itself overnight and peak_equity reset "
  "to $300, so the -20% drawdown lock could never fire.",
  "state/ tracked in git; .gitignore reduced to secrets only, with a comment "
  "forbidding the lines' return. state.load() warns loudly and tags the "
  "ledger `reborn` when it is missing.",
  "2026-09-15 11:18", "2026-09-15 20:47", "2026-09-15 20:47",
  "0", "cd3f0b3", "Closed"),
 ("B-04", "Governance", "Critical",
  "`propose_from_plan(today) or propose_mechanical(...)`: an empty plan is [] "
  "and therefore falsy, so a deliberate NO-TRADE decision silently handed "
  "control to the 20-day-breakout scanner. Harmless on the day only because "
  "the scanner also found nothing.",
  "`is None` distinguishes 'no plan written' from 'plan says trade nothing'. "
  "An empty plan returns before the scanner is reached.",
  "2026-09-15 18:36", "2026-09-16 15:17", "2026-09-16 15:17",
  "1", "6c70fe7", "Closed"),
 ("B-05", "Governance", "Critical",
  "NO_TRADE and RISK_OFF postures had no enforcement in any .py file — they "
  "appeared once, inside a comment. The brief's posture, documented as "
  "binding, was enforced only by the model's own compliance.",
  "engine/posture.py parses the brief and returns hard limits; paper_session "
  "applies them before any proposal is evaluated.",
  "2026-09-15 18:36", "2026-09-16 15:17", "2026-09-16 15:17",
  "1", "6c70fe7", "Closed"),
 ("B-06", "Record integrity", "High",
  "review.closed_trades() had no dry_run filter, so previewed tickets accrued "
  "toward the 30 closed trades and the expectancy that unlock the option "
  "sleeve, and a phantom dry-run entry sat at the head of the FIFO queue "
  "waiting to corrupt the next real trade's entry price and R.",
  "closed_trades() drops dry_run rows before pairing, with a docstring "
  "explaining both failure modes.",
  "2026-09-15 18:36", "2026-09-16 15:17", "2026-09-16 15:17",
  "1", "6c70fe7", "Closed"),
 ("B-07", "Infrastructure", "Critical",
  "The first autonomous Routine firing failed immediately: create_trigger "
  "carries no git source, because a fresh-session-on-fire inherits the "
  "environment, not the repository. The container came up empty.",
  "Firings bound to a repo-attached persistent session instead of "
  "create_new_session_on_fire. preflight_phase2 gained a `repository` check "
  "as its first test.",
  "2026-09-15 20:51", "2026-09-16 15:11", "2026-09-16 15:31",
  "1", "70f8dbd, e904c36", "Closed"),
 ("B-08", "Monitoring", "High",
  "netcheck treated HTTP 403 as healthy, and checked its bot-challenge "
  "markers only against success bodies. Five of six news sources and two "
  "primary sources were serving walls and reporting green.",
  "403 maps to DEGRADED; challenge markers extended and checked against error "
  "bodies too; required and primary tiers separated so a primary outage "
  "degrades rather than halts.",
  "2026-09-15 19:11", "2026-09-17 15:32", "2026-09-17 15:32",
  "2", "02a4246", "Closed"),
 ("B-09", "Governance", "High",
  "The posture parser read the brief's reasoning text rather than its "
  "decision, so a brief explaining why it was NOT going risk-off could be "
  "parsed as RISK_OFF (or the reverse).",
  "Parser anchored and made to fail closed: an unparseable posture is treated "
  "as the most restrictive, not the least.",
  "2026-09-16 15:17", "2026-09-17 15:32", "2026-09-17 15:32",
  "1", "02a4246", "Closed"),
 ("B-10", "Universe", "High",
  "'No setup today' was being computed against six hardcoded tickers. Two "
  "sessions reported a quiet market when nothing had screened a market.",
  "tools/screen.py builds and commits a 150-symbol universe from Alpaca "
  "assets with price, volume and exchange criteria; the skill must state the "
  "denominator it screened.",
  "2026-09-15 18:36", "2026-09-17 15:38", "2026-09-17 15:38",
  "2", "81c461f", "Closed"),
 ("B-11", "Data path", "High",
  "The keyless Yahoo fallback was a hard preflight dependency. It rate-limits "
  "under load, so it could cancel a trading day on which Alpaca was healthy.",
  "preflight gates on Alpaca; Yahoo demoted to cross-check only.",
  "2026-09-15 20:03", "2026-09-17 16:12", "2026-09-17 16:12",
  "2", "269f363", "Closed"),
 ("B-12", "Data access", "Medium",
  "The outbound User-Agent claimed to be Mozilla, and .gov WAFs gated it.",
  "Honest identification with a contact address, via "
  "tools.netcheck.user_agent() and TRADING_AGENT_CONTACT; marketdata.py "
  "imports it rather than keeping its own string.",
  "2026-09-15 20:03", "2026-09-17 16:12", "2026-09-17 16:12",
  "2", "269f363", "Closed"),
 ("B-13", "Integration", "High",
  "After a week of source work, no skill referenced adapters.fred, "
  "tools.screen, the committed universe, the Alpaca news API or any RSS feed. "
  "news-intel still named six outlets verified that morning as bot walls. "
  "Every capability was built, verified, and called by nothing.",
  "news-intel, premarket-brief and trade-plan rewritten to name only "
  "verified-working sources and to call the tools that exist.",
  "2026-09-17 17:11", "2026-09-17 17:18", "2026-09-17 17:18",
  "0", "56796ac", "Closed"),
 ("B-14", "Risk gate", "Critical",
  "The 'expected R >= 1.5' rule existed only in prose. "
  "RiskOfficer.evaluate() never read OrderProposal.target, so the gate was "
  "unreachable by construction. The simulator could not detect it: every "
  "strategy sets target = entry + 3*ATR against a 1.5*ATR stop, which is 2.0R "
  "by construction and can never fail a 1.5 gate.",
  "min_expected_r and require_target in config; the gate in risk.py after the "
  "asset-class checks, with a 1e-9 epsilon because the config's own option "
  "exit pair is 0.60/0.40 = 1.4999999999999998. 7 tests.",
  "2026-09-15 18:36", "2026-09-18 18:33", "2026-09-18 18:33",
  "3", "5ff6999", "Closed"),
 ("B-15", "Record integrity", "Critical",
  "paper_session --submit wrote a fill-log row for every accepted order, at "
  "the PROPOSED price and approved quantity, with no check that anything "
  "traded. A bracket limit can rest all day and expire unfilled and would "
  "still have been recorded as an entry — feeding the option-unlock gate and "
  "corrupting the next real trade in that symbol via FIFO pairing. Invisible "
  "for two sessions because the live path had never executed.",
  "AlpacaAdapter.order()/await_fill() poll to a terminal status; "
  "fill_record() is a pure function that writes only real fills at the "
  "broker's price and quantity. Unfilled orders go to ledger.working_orders. "
  "10 tests.",
  "2026-09-15 18:36", "2026-09-18 18:36", "2026-09-18 18:36",
  "3", "9d0a264", "Closed"),
 ("B-16", "Execution", "Critical",
  "A bracket's protective legs inherit the parent's time_in_force, which "
  "defaulted to 'day'. A position filled at 10:15 had its stop CANCELLED at "
  "16:00 while the position stayed open, and went through the overnight gap "
  "naked. positions_without_stops() would have reported it the next morning, "
  "which is after the gap.",
  "OrderTicket.time_in_force defaults to 'gtc'. trading_day close cancels "
  "resting ENTRY orders only (identified by still carrying their `legs`) and "
  "re-verifies stops afterwards. cancel_all() explicitly rejected for this "
  "job: it would strip live legs off open positions. 3 tests.",
  "2026-09-15 18:36", "2026-09-18 18:40", "2026-09-18 18:40",
  "3", "3418309", "Closed"),
 ("B-17", "Infrastructure", "Medium",
  "The repository path is not stable within a scheduled session, so tools "
  "invoked with a remembered absolute path failed on later turns.",
  "Discover the repo root every turn rather than caching it.",
  "2026-09-16 15:11", "2026-09-16 15:13", "2026-09-16 15:13",
  "0", "b5624ac", "Closed"),
 ("B-19", "Execution", "Critical",
  "cancel_unfilled_entries() cancelled nothing. It identifies an unfilled "
  "bracket parent by the presence of its `legs`, but "
  "GET /v2/orders?status=open omits nested legs entirely — the parent comes "
  "back with no legs at all. The close would have carried resting entries "
  "into the next session while reporting success.",
  "Query with nested=true. open_orders() keeps its flat default because "
  "positions_without_stops depends on a filled parent's live legs appearing "
  "top-level. A type guard added so a stop can never be cancelled by this "
  "method even if the response shape changes again.",
  "2026-09-18 18:40", "2026-09-18 18:52", "2026-09-18 18:55",
  "0", "4e5da64", "Closed"),
 ("B-20", "Monitoring", "Critical",
  "positions_without_stops() counted a TAKE-PROFIT as a stop. It marked a "
  "symbol protected on `order_class in (bracket, oto, oco)`. Filling a "
  "bracket live showed the take-profit leg surfacing first carrying "
  "order_class 'bracket' while the stop leg sat `held` — and Alpaca's "
  "status=open filter excludes held. With the stop genuinely cancelled and "
  "the take-profit intact — exactly the state B-16 produced — this control "
  "would still have reported the position protected, and it is the check "
  "that decides whether the close escalates.",
  "Requires a real order, of a stop type, in a status that can still execute, "
  "read from a nested listing so held legs are visible. 5 tests.",
  "2026-09-15 18:36", "2026-09-18 18:53", "2026-09-18 18:55",
  "3", "4e5da64", "Closed"),
 ("B-21", "Data path", "Critical",
  "AlpacaAdapter.bars() pinned feed=iex because the free plan was BELIEVED to "
  "serve nothing else. It serves sip. IEX is one venue carrying a median 3.8% "
  "of consolidated volume, and a 3.8% sample does not misprice a mean — "
  "prices agree to the cent — it misprices an EXTREMUM, which is the only "
  "statistic this series is used for. Across 59 universe names: ATR(14) "
  "IEX/SIP median 0.976, worst 0.571, SMALLER IN 59 OF 59; the 20-day high "
  "understated in 43/59 (worst -0.913%); the 20-day low overstated in 41/59. "
  "One-directional every time, arithmetically rather than statistically: a "
  "subset of prints cannot contain a higher high or a lower low than the "
  "whole, so it could never average out with more data. Consequences: phantom "
  "breakouts (1 in 59; RKLB fired at 70.76 against a true 71.21 level), every "
  "stop too tight in 59/59 names, and every support level too high. Dollar "
  "risk at the stop survives because size follows the stop — the share count "
  "does not, so gap exposure scales with the error.",
  "Not a blanket feed swap: SIP is 15 MINUTES DELAYED on this plan and "
  "/v2/stocks/snapshots rejects feed=sip, while paper_session was reading "
  "bars[-1].close as the entry price. So completed sessions come from SIP "
  "(where a delay cannot matter), the price now comes from a new real-time "
  "last_trade() that returns None rather than a guess, and breakout_now() "
  "takes the level and the price from different sources by construction. "
  "8 tests including one pinning the RKLB phantom against both tapes.",
  "2026-09-15 18:36", "2026-09-22 13:50", "2026-09-22 16:20",
  "7", "7c0c97e", "Closed"),
 ("B-22", "Data path", "High",
  "build_universe() read snapshot `dailyBar`, which during the session is a "
  "PARTIAL bar. Building at 09:50 ET measured twenty minutes of volume "
  "against a full-day floor, so a $1.5M threshold behaved like ~$30M/day and "
  "dropped MARA, CMCSA, MNST, ZTS, TFC and KR — all plainly liquid. Measured "
  "at 11:58 the same day, today's dollar volume ran 0.25x to 1.46x of the "
  "prior completed session across ten names. Worse than wrong, it was not "
  "REPRODUCIBLE: the scan walks ~11,800 assets over several minutes, so the "
  "effective floor moved during a single build — KR was excluded while the "
  "build ran and passed minutes later.",
  "prevDailyBar, a completed session, identical at 09:31 and 15:59. Universe "
  "110 -> 150 (the size cap binding again rather than the floor), all six "
  "names back. Two consecutive builds now produce identical symbol lists, "
  "identical dollar volumes and an identical session label. The IEX "
  "calibration is untouched and still correct — snapshots cannot serve SIP.",
  "2026-09-15 18:36", "2026-09-22 13:45", "2026-09-22 16:20",
  "7", "7c0c97e", "Closed"),
 ("B-23", "Controls", "High",
  "The M-22 attendance gate never bound, once, ever. is_attended() read "
  "CLAUDE_CODE_SESSION_ATTENDED, which is set ENVIRONMENT-WIDE, so it read "
  "'1' in every session including unattended scheduled firings. Demonstrated "
  "end to end: an unattended relay ran model_check --model claude-opus-5 "
  "rule-promotion and got exit 0. It shipped in the SAME COMMIT as the fix "
  "for two other instances of this exact pattern, one function below a "
  "comment warning that a blocking task must not clear on a value that cannot "
  "vary with the thing being checked.",
  "The first proposed fix — require the variable to equal "
  "CLAUDE_CODE_SESSION_ID — was also wrong: a scheduled relay fired into "
  "session 38d73c9c unattended at 14:20Z and a human typed into it at 15:45Z, "
  "same id and environment throughout. ATTENDANCE IS A PROPERTY OF THE TURN, "
  "and env vars are snapshotted at session start, so no variable of any scope "
  "can track it. The gate no longer detects: a blocking task requires "
  "--authorization '<why, in the human's words>', appended to "
  "state/authorizations.jsonl. Trivial strings refused; verbatim reuse "
  "refused, so it cannot be baked into a Routine prompt and fired on a "
  "schedule. Attributable, not enforceable, and documented in those words.",
  "2026-09-21 21:40", "2026-09-22 14:30", "2026-09-22 15:50",
  "1", "37f86a1", "Closed"),
 ("B-24", "Reporting", "Low",
  "The universe build report printed 'min $2M dollar volume' for a $1.5M "
  "floor — .0f applied to 1.5. Anyone auditing the universe would have "
  "recorded a threshold the code does not use.",
  "Formatted to 2dp and the liquidity session named alongside it.",
  "2026-09-15 18:36", "2026-09-22 16:10", "2026-09-22 16:15",
  "7", "7c0c97e", "Closed"),
 ("B-25", "Reporting", "Medium",
  "A provenance field added during the B-22 fix was wrong within the hour. "
  "`liquidity_session` took whichever symbol the API returned first, and a "
  "name that had not traded in a week carries a week-old prevDailyBar — so "
  "two builds selecting IDENTICAL universes labelled themselves 2026-09-14 "
  "and 2026-09-21. Caught only by the reproducibility check written for B-22. "
  "A provenance field that is wrong is worse than none, because it is "
  "believed; and it was written while fixing two bugs of exactly its kind.",
  "The mode across the names that actually made the universe, with any other "
  "sessions listed explicitly in other_sessions_present. Test pins it.",
  "2026-09-22 16:05", "2026-09-22 16:12", "2026-09-22 16:18",
  "0", "7c0c97e", "Closed"),
 ("B-26", "Controls", "Medium",
  "The trading day was the CONTAINER's date, not the exchange's. "
  "drift_today() keyed on dt.date.today() and matched UTC timestamps by "
  "string prefix. UTC midnight is 20:00 ET — four hours after the close but "
  "on the same session's evening — so the drift window opened the previous "
  "evening: the 2026-09-22 close counted a reading from Monday 22:32 ET. It "
  "was also decided by the HOST, since the same code on an ET machine "
  "compares an ET date against UTC strings and buckets differently or "
  "matches nothing. Harmless at zero drift; not harmless once the cumulative "
  "figure feeds drift_halts, and crypto fills around the clock.",
  "One named trading_date() on ZoneInfo('America/New_York') rather than a "
  "fixed -05:00, so DST is carried rather than remembered. EVERY 'today' in "
  "the module moved to it — open, close, preclose, week key, day-start key — "
  "because a drift window on ET and halt baselines on UTC would be worse "
  "than either alone. 7 tests; suite green under four timezones. Two faults "
  "occurred INSIDE the fix, both the same bug: the test mock no longer "
  "reached the moved seam, and the replacement helper pinned the conversion "
  "as well as the clock, relabelling Friday as Monday.",
  "2026-09-15 18:36", "2026-09-22 20:07", "2026-09-23 04:05",
  "7", "48353b4", "Closed"),
 ("B-27", "Reporting", "Medium",
  "Three of five Phase 2 exit criteria passed VACUOUSLY, so an account that "
  "had never traded printed three [ok]s and read three-fifths of the way to "
  "Phase 2 exit. all() over an empty list is True, and 'costs below gains' "
  "carried an explicit `if trades else True`. Each is a defensible vacuous "
  "truth alone; together they made inactivity look like progress. Same shape "
  "as 'no protective leg was stripped — vacuously, with no position', but in "
  "a published scorecard rather than a session note.",
  "Three states: [ok], [XX], and [--] not yet measurable, with the exit gate "
  "requiring every criterion to be measurable AND passed. Measurability keys "
  "on TRADES, not sessions observed — the first attempt used sessions and "
  "still printed two [ok]s, because you cannot breach a rail you never "
  "touched and LOCKED needs a -20% drawdown, which needs losses. A guardrail "
  "never exercised was not honoured, it was untested. A flat account now "
  "reads 0/5. 4 tests.",
  "2026-09-15 18:36", "2026-09-22 20:07", "2026-09-23 04:05",
  "7", "48353b4", "Closed"),
 ("B-28", "Controls", "Medium",
  "CLAUDE_EFFORT is NOT snapshotted at session start, contrary to CLAUDE.md. "
  "Measured within one session on 2026-09-22: high at 13:39Z, medium at "
  "20:07Z. It tracks the TURN. model_check runs ONCE at task start and "
  "nothing re-reads it, so a blocking task that clears at xhigh can perform "
  "its durable write at medium with no signal; session-close ran two notches "
  "below its floor that evening. Third member of a family found in two days: "
  "attendance is a property of the turn (B-23), effort is a property of the "
  "turn, and both were read as though they described a session.",
  "PARKED, not wired in, at recalcitrantmaus's request — to be incorporated "
  "deliberately at the end of a session rather than dropped into a live "
  "trading day. recheck() re-reads effort at the DURABLE WRITE rather than "
  "at task start, because that is where a downgrade costs something. It does "
  "not re-verify the model: passing --model is a human's act, already "
  "recorded and single-use. 6 tests, one of which fails the moment anyone "
  "wires it in.",
  "2026-09-20 00:00", "2026-09-22 20:07", "",
  "2", "48353b4", "PARKED — activate at a session end"),
 ("B-18", "Permissions", "High",
  "`python3 -m tools.paper_session --submit` is refused by the permission "
  "classifier as a real-world transaction, so the live session path cannot "
  "run unattended. There is no .claude/settings.json in the repository — no "
  "permission allowlist exists at all.",
  "OPEN. A project-level .claude/settings.json allowlist is drafted in "
  "docs/11-autonomous-permissions.md. Claude cannot write it: the auto-mode "
  "classifier blocks agent edits to .claude/ as self-modification, which is "
  "correct. A human must install it.",
  "2026-09-15 11:18", "2026-09-18 14:01", "",
  "3", "", "OPEN — needs human"),
]

# --------------------------------------------------------------------------
# Sheet 3 — systems and APIs in use
# --------------------------------------------------------------------------
SYSTEMS_COLS = ["Name", "Kind", "Host / endpoint", "Purpose", "Auth",
                "Tier", "Verified", "Notes"]
SYSTEMS = [
 ("Alpaca paper trading", "Broker API", "paper-api.alpaca.markets",
  "Phase 2 order routing, account, positions, orders, clock",
  "API key + secret (env)", "Required", "2026-09-18",
  "Bracket orders confirmed with 2 attached legs. Rejects fractional "
  "brackets and all advanced crypto order classes."),
 ("Alpaca market data", "Market data API", "data.alpaca.markets",
  "Bars (SIP for completed sessions, IEX for the live price), snapshots, "
  "most-actives screener, and the news API (/v1beta1/news)",
  "API key + secret (env)", "Required", "2026-09-22",
  "THIS PLAN SERVES feed=sip, which was not known until 2026-09-22 and cost "
  "bug B-21. SIP is CONSOLIDATED but 15 MINUTES DELAYED (measured: IEX last "
  "minute-bar 16:03Z, SIP 15:49Z). IEX is real-time but a single venue at a "
  "median 3.8% of consolidated volume, which leaves means right and EXTREMA "
  "wrong — 20-day highs understated, lows overstated, ATR smaller in 59 of 59 "
  "names. So: completed sessions from SIP, the price now from IEX via "
  "last_trade(). /v2/stocks/snapshots REJECTS feed=sip, so the universe's "
  "dollar-volume floor stays in IEX units and its ~4% calibration stands "
  "(measured 3.8%). News feed is Benzinga only, 50 of 50 items, so it cannot "
  "corroborate itself under the two-lane rule."),
 ("Alpaca live trading", "Broker API", "api.alpaca.markets",
  "Phase 3 only. Never reachable from tools.paper_session, which hardcodes "
  "live=False", "API key + secret (env)", "Required (Phase 3)", "2026-09-18",
  "Guarded by Authorization.load() — a dated human authorization file with a "
  "max order notional — plus confirm_live=True at the call site."),
 ("Robinhood agentic MCP", "Broker MCP", "agent.robinhood.com/mcp/trading",
  "Phase 3 order routing: long equities, options and crypto on a dedicated "
  "pre-funded account", "OAuth / MCP connector", "Required (Phase 3)",
  "2026-09-17",
  "Leg time-in-force inheritance must be re-measured here before Phase 3 — "
  "it is broker behaviour, not a standard (see B-16)."),
 ("FRED", "Macro data", "fred.stlouisfed.org",
  "Jobless claims, retail sales, 10Y, 10Y-2Y, HY spreads, CPI, unemployment, "
  "VIX, SOFR as keyless CSV", "None", "Primary", "2026-09-17",
  "adapters/fred.py drops '.' missing values rather than zeroing them, and "
  "returns as_of and stale_days with every value. Carries the jobless-claims "
  "print that www.dol.gov refuses us."),
 ("SEC EDGAR", "Filings", "www.sec.gov", "Company filings, primary facts",
  "None (identified UA required)", "Primary", "2026-09-17",
  "Requires an honest User-Agent with a contact address."),
 ("SEC company facts", "Filings API", "data.sec.gov",
  "XBRL company concepts as JSON", "None (identified UA required)",
  "Primary", "2026-09-17", "Probe returned 11 USD facts for Apple."),
 ("Federal Reserve", "Macro", "www.federalreserve.gov",
  "Statements and calendar", "None", "Primary", "2026-09-17", ""),
 ("BLS", "Macro", "www.bls.gov", "CPI and jobs — the release, not a summary",
  "None", "Primary", "2026-09-17", ""),
 ("BEA", "Macro", "www.bea.gov", "GDP, PCE", "None", "Primary",
  "2026-09-17", ""),
 ("US Treasury", "Macro", "home.treasury.gov", "Yield curve, auctions",
  "None", "Primary", "2026-09-17", ""),
 ("Treasury fiscal data", "Macro API", "api.fiscaldata.treasury.gov",
  "Fiscal data as JSON", "None", "Primary", "2026-09-17", ""),
 ("New York Fed", "Macro", "www.newyorkfed.org",
  "SOFR and reference rates", "None", "Primary", "2026-09-17", ""),
 ("CFTC", "Positioning", "publicreporting.cftc.gov",
  "Commitments of Traders", "None", "Primary", "2026-09-17", ""),
 ("FINRA", "Rules", "www.finra.org",
  "Day-trading and margin rules — verify before Phase 3", "None", "Primary",
  "2026-09-17",
  "FINRA replaced the PDT $25k regime with intraday margin standards "
  "effective 2026-06-04, broker phase-in to 2027-10-20. The config models the "
  "strict case until Robinhood's implementation is confirmed."),
 ("EIA", "Commodities", "www.eia.gov", "Energy inventories", "None",
  "Optional", "2026-09-17", ""),
 ("Yahoo Finance", "Market data", "query1.finance.yahoo.com",
  "Independent price cross-check", "None", "Optional", "2026-09-18",
  "Undocumented and rate-limits under load. Must never gate a trading day "
  "(B-11). Used by adapters.marketdata.cross_check() with a 50bps tolerance."),
 ("CoinGecko", "Crypto prices", "api.coingecko.com",
  "Crypto prices, free tier", "None", "Optional", "2026-09-17",
  "Reference only. No crypto is traded (D-21)."),
 ("CoinDesk", "News", "www.coindesk.com",
  "Crypto coverage — the one news HTML host that serves us", "None",
  "Optional", "2026-09-17", ""),
 ("BBC business RSS", "News", "feeds.bbci.co.uk", "Business headlines",
  "None", "News", "2026-09-17", "RSS; the HTML pages are bot-walled."),
 ("NPR business RSS", "News", "feeds.npr.org", "Business headlines", "None",
  "News", "2026-09-17", ""),
 ("Guardian business RSS", "News", "www.theguardian.com",
  "Business headlines", "None", "News", "2026-09-17", ""),
 ("Fox Business RSS", "News", "moxie.foxbusiness.com", "Markets headlines",
  "None", "News", "2026-09-17", "Carries the political spread the skill asks for."),
 ("The Hill business RSS", "News", "thehill.com", "Business headlines",
  "None", "News", "2026-09-17", ""),
 ("Cointelegraph RSS", "News", "cointelegraph.com", "Crypto headlines",
  "None", "News", "2026-09-17", ""),
 ("Decrypt RSS", "News", "decrypt.co", "Crypto headlines", "None", "News",
  "2026-09-17", ""),
 ("Claude Code Remote Routines", "Scheduler", "claude-code-remote MCP",
  "Scheduled session firings at open, midday, pre-close and close",
  "Session-scoped", "Required", "2026-09-18",
  "Must bind to a repo-attached persistent session: a fresh-session-on-fire "
  "inherits the environment, not the repository (B-07)."),
 ("GitHub", "Source control", "github.com/recalcitrantmaus/tradingagent-claude",
  "The repository is the durable state — containers are reclaimed",
  "MCP / session-scoped", "Required", "2026-09-18",
  "state/ is tracked deliberately so circuit breakers survive a fresh clone "
  "(B-03)."),
 # --- verified dead; kept so they are not silently re-added ---
 ("stooq.com", "Market data", "stooq.com", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 200 with a JavaScript bot challenge instead of data."),
 ("Reuters", "News", "www.reuters.com", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 401 + bot challenge."),
 ("MarketWatch", "News", "www.marketwatch.com", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 401 + bot challenge."),
 ("AP News", "News", "apnews.com", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 403 + bot challenge."),
 ("The Block", "News", "www.theblock.co", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 403 + bot challenge."),
 ("CNBC", "News", "www.cnbc.com", "(removed)", "None", "DEAD",
  "2026-09-17", "HTTP 403."),
 ("US Census", "Macro API", "api.census.gov", "(removed)", "API key",
  "DEAD", "2026-09-17",
  "HTTP 200 carrying an HTML 'Missing Key' page. FRED serves the same "
  "retail-sales series (RSAFS) without a key."),
 ("US Dept of Labor", "Macro", "www.dol.gov", "(removed)", "None", "DEAD",
  "2026-09-17", "Refuses us; FRED's ICSA carries the same print."),
]


def build():
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl is not installed.  pip install openpyxl", file=sys.stderr)
        return 1

    HEAD_FILL = PatternFill("solid", fgColor="1F3864")
    HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
    OPEN_FILL = PatternFill("solid", fgColor="FFF2CC")
    DEAD_FILL = PatternFill("solid", fgColor="F2F2F2")

    wb = Workbook()
    wb.remove(wb.active)

    def sheet(title, cols, rows, widths, wrap_from=0, highlight=None):
        ws = wb.create_sheet(title)
        ws.append(cols)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for c in range(1, len(cols) + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill, cell.font = HEAD_FILL, HEAD_FONT
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            ws.append(list(r))
        for row in ws.iter_rows(min_row=2):
            for c, cell in enumerate(row):
                cell.alignment = Alignment(
                    vertical="top", wrap_text=(c >= wrap_from))
            if highlight:
                fill = highlight([c.value for c in row])
                if fill:
                    for cell in row:
                        cell.fill = fill
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    sheet("Design decisions", DECISIONS_COLS, DECISIONS,
          [8, 12, 16, 46, 60, 34, 40, 10], wrap_from=3)

    def bug_fill(vals):
        return OPEN_FILL if vals[-1].startswith("OPEN") else None
    sheet("Bugs", BUGS_COLS, BUGS,
          [7, 18, 10, 72, 62, 20, 18, 18, 12, 16, 16],
          wrap_from=3, highlight=bug_fill)

    def sys_fill(vals):
        return DEAD_FILL if vals[5] == "DEAD" else None
    sheet("Systems & APIs", SYSTEMS_COLS, SYSTEMS,
          [26, 16, 38, 44, 26, 18, 12, 62], wrap_from=3, highlight=sys_fill)

    # A front sheet, so the workbook says what it is and how to rebuild it.
    ws = wb.create_sheet("About", 0)
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip() or "unknown"
    for row in [
        ["Trading agent — design documentation"],
        [],
        ["Generated from", "tools/design_doc.py at commit " + rev],
        ["Rebuild with", "python3 -m tools.design_doc"],
        [],
        ["This workbook is a build artifact.", "Edit tools/design_doc.py, not "
         "the .xlsx — edits here are overwritten on the next build."],
        [],
        ["Design decisions", f"{len(DECISIONS)} rows. Each cites the file that "
         "enforces it and the evidence that justified it."],
        ["Bugs", f"{len(BUGS)} rows. 'Created' is when the defect entered the "
         "codebase per git log, not when it was noticed; 'Days latent' is the "
         "gap, i.e. how long the system looked correct while being wrong."],
        ["Systems & APIs", f"{len(SYSTEMS)} rows, including sources verified "
         "DEAD, kept so they are not silently re-added."],
        [],
        ["Open items", f"{sum(1 for b in BUGS if b[-1].startswith('OPEN'))} "
         "(highlighted on the Bugs sheet)"],
    ]:
        ws.append(row)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 100
    ws["A1"].font = Font(bold=True, size=14)
    for r in ws.iter_rows(min_row=3):
        r[0].font = Font(bold=True)
        for cell in r[1:]:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}  "
          f"({len(DECISIONS)} decisions, {len(BUGS)} bugs, "
          f"{len(SYSTEMS)} systems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
