# Roadmap: stages, gates and activities

Drafted 2026-09-29 for recalcitrantmaus to put timelines against. The timeline column is
deliberately blank.

**How this maps to the older wording.** The repo used "Phase 1/2/3" (build,
paper, live). "Stage 3" in the 2026-09-28 conversation meant step 3 of an
effort recommendation, not a phase. This roadmap replaces both. Phase 2 is
split into three stages, because it has been answering three separate
questions:
- whether the plumbing works;
- whether it runs without a person;
- whether the strategy has an edge.

Phase 2's exit list (`docs/07-deployment.md` §5) requires "the same model
configuration you intend to run live". So **Autonomy must finish before
Evidence starts counting**: trades taken on a configuration that later changes
do not count toward the 30.

| # | Stage | Old name | Status |
|---|---|---|---|
| 1 | **Build** | Phase 1 | done |
| 2 | **Plumbing** | Phase 2 | current |
| 3 | **Autonomy** | (new) | started: effort pin, Managed Agents design |
| 4 | **Evidence** | Phase 2 exit | not started |
| 5 | **Live Pilot** | Phase 3 | not started |
| 6 | **Scale** | (new) | not started |

---

## 1. Build (done)

- **Entry:** feasibility accepted (`docs/01-feasibility.md`).
- **Key activities:**
  - Risk engine and circuit breakers.
  - Simulator and Monte Carlo suite.
  - Skills.
  - Regression discipline.
- **Exit:**
  - Every capital rule is code with a test.
  - `sim.run_suite` shows 0% ruin at 300 seeds.
  - Guardrail behaviour is documented (`docs/05-sim-report.md`).

## 2. Plumbing (current)

- **Entry:**
  - Alpaca paper account and keys.
  - Network open.
  - Routines able to fire unattended.
- **Key activities:**
  - Run daily firings.
  - Fix each finding as a regression test (the G-n queues).
  - Permissions (F-1), relay, news lanes (G-3), scanner check (G-4).
- **Exit, each observed at least once, unattended, on the order path:**
  - [ ] An open **submits** an order under the allow-listed command form
  - [ ] The fill reconciles, with the stop resting GTC, and `broker_check` exits 0
  - [ ] The management path acts: a scale-out or trail, and an overnight carry
  - [ ] The posture gate blocks a real order
  - [ ] An empty plan binds against a scanner that disagrees
  - [x] Reports reach the arming session with no human relay (2026-09-28)
  - [ ] G-4 settled: the scanner's zero is either real or fixed

## 3. Autonomy

- **Entry:** can start alongside Plumbing, and must finish before Evidence
  counts.
- **Key activities:**
  - Pin effort. Short term: `modelSettings` or `CLAUDE_CODE_EFFORT_LEVEL`.
    Long term: on the Managed Agent.
  - Run the POC (`tools/ma_poc.py`).
  - Move the firings to scheduled deployments, with vault credentials.
  - `model_check` reads the stored agent.
  - Below-floor at the open means no new entries (needs authorization).
  - Reporting by run records and webhooks.
  - Spend caps.
- **Exit:**
  - [ ] 10 consecutive trading days with **no human action**: no picker, no
    re-arming, no relay
  - [ ] Zero missed firings. Every firing's run record exists, and failures
    are alerted
  - [ ] Effort readback equals the pin on every firing
  - [ ] Daily cost is measured and within a budget recalcitrantmaus sets
  - [ ] The configuration is frozen and recorded. This is the one Evidence
    counts under

## 4. Evidence

- **Entry:** Autonomy exit, with the configuration frozen.
- **Key activities:**
  - Accrue paper trades.
  - Weekly reviews.
  - Change rules only with evidence (CLAUDE.md "Changing a rule").
  - Earn the Opus data floor down with deterministic checks.
- **Exit (the Phase 2 list, unchanged):**
  - [ ] 30+ closed paper trades
  - [ ] Positive measured expectancy (`tools.review`)
  - [ ] Zero guardrail breaches
  - [ ] Costs below realized gains
  - [ ] Every thesis traceable to a source URL
  - [ ] Run on the configuration intended for live
- **Timeline input:** 1 closed trade since inception (`tools.review`,
  2026-09-28). The trade rate is the unknown that sets this stage's length.
  Estimate it after Autonomy, not before.

## 5. Live Pilot

- **Entry:**
  - Evidence exit.
  - recalcitrantmaus's explicit go.
  - A Robinhood agentic account, funded.
  - The connector attached to the deployment (`docs/07-deployment.md` §6).
  - Kill switches verified live (§4).
- **Key activities:**
  - Same rules and same sizes, with real money.
  - Reconcile against Robinhood.
  - Compare live fills with the paper and slippage models.
- **Exit:**
  - [ ] 30 closed live trades
  - [ ] Live expectancy is positive, and not materially below paper
  - [ ] Zero reconciliation breaks
  - [ ] Slippage within the modelled costs

## 6. Scale

- **Entry:** Live Pilot exit.
- **Key activities:**
  - Grow toward $1,500, "the real first milestone" (CLAUDE.md).
  - Decide on the options sleeve. It stays locked until **both** $1,500 equity
    **and** 30+ trades at >= +0.10R (`engine/config.py`).
  - Set a capital-addition policy.
- **Exit:** open-ended. Reviewed quarterly.

---

**Standing rules across every stage:**
- The 5%/week target is a hurdle to report against, never a gate.
- No stage exit is ever met by a good week.
