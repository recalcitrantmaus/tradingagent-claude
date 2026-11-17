# tradingagent-claude

An autonomous trading agent for a small ($300) account, built so that the
parts which can lose money are deterministic, tested code and the parts which
need judgment are LLM skills.

**One rule outranks everything: the model decides what to trade; code decides
whether it is allowed.** If `RiskOfficer.evaluate` rejects an order, the
correct action is to record the rejection and move on — never to reshape the
order until it passes. That behaviour is the failure mode this whole system
exists to prevent.

## Status — paused 2026-09-29

Built over two weeks, 2026-09-15 to 2026-09-29, and paused after the Monday
2026-09-28 session. Nothing is armed and the paper account is flat.

**Why it is paused.** At this account size, running and maintaining an
autonomous agent cost more than it returned compared with working through
market questions directly with Claude. The repository stays up as the record
of the design, the evidence and the lessons.

**Who built it.** Designed and directed by recalcitrantmaus; the code was
written with Claude Code. Every rule change the owner approved is logged, dated and
signed in [`state/authorizations.jsonl`](state/authorizations.jsonl).

| | |
|---|---|
| Account | $300 Alpaca **paper** account, flat at $299.62, risk state NORMAL |
| Live paper trading | 2026-09-15 to 2026-09-28, sessions fired unattended on scheduled Claude Code routines |
| Closed trades | **1** (DT, −$0.37, −0.139R). Most sessions found nothing that cleared the gate and stood down, which is the design working. Phase 2 exit needs 30+ closed trades at ≥ +0.10R. |
| Tests | 469. In a fresh environment 467 pass; the other 2 expect Alpaca paper keys to be set. |
| Simulation | 300-seed Monte Carlo per arm; sweeps up to 3,000 seeds |
| Live market data | 2,472 symbols, daily bars 2021–2026, consolidated tape |

**One closed trade is not evidence.** The live edge is unmeasured, and the
paths that only a steady flow of fills would exercise are still thinly tested
against reality. A flat account is an absence of evidence, not evidence that
the guardrails work — `trading_day week` says so explicitly rather than
printing `[ok]` on criteria nothing has tested.

**Picking it back up? Start with [`HANDOFF.md`](HANDOFF.md), then `CLAUDE.md`.**

## Read these first

| Document | Why |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | The agent's operating instructions — the binding ones |
| [`docs/01-feasibility.md`](docs/01-feasibility.md) | What $300 can and cannot do, with the arithmetic |
| [`docs/02-architecture.md`](docs/02-architecture.md) | How the pieces fit, and exactly what the gate checks |
| [`docs/04-lessons.md`](docs/04-lessons.md) | **Every rule and the evidence behind it** — and every bug, including the ones introduced while fixing others |
| [`docs/05-sim-report.md`](docs/05-sim-report.md) | Phase 1 simulation: what was tested, what broke, what changed |
| [`docs/12-session-flow.md`](docs/12-session-flow.md) | What happens at each firing, as diagrams |
| [`docs/16-entry-study.md`](docs/16-entry-study.md) | Chase vs retest over six years, and why the one-year answer was wrong |
| [`docs/07-deployment.md`](docs/07-deployment.md) | Running it autonomously: routing, broker, kill switches |
| [`docs/09-phase2-runbook.md`](docs/09-phase2-runbook.md) | The daily and weekly Phase 2 loop |
| [`docs/design-documentation.xlsx`](docs/design-documentation.xlsx) | Every decision, bug and external system, as a spreadsheet (generated) |

## What the evidence says

**On the target.** 5%/week compounds to +1,164% annualized. Treated as a
hurdle rate it is harmless; treated as a quota it is fatal. The strategy that
pursued it most directly hit the −20% lock in **100% of 300 simulated years**,
winning 3.2% of its trades. With guardrails removed, option trading on $300
**ruined 94% of accounts** while hitting +5% weeks *more often* than the
disciplined strategy. Optimizing the stated KPI selects for ruin.

**On options.** Unaffordable at $300 *and* unprofitable at every size tested —
a sweep from $300 to $10,000 found long-premium buying negative everywhere. So
the sleeve is gated on *measured edge*, not on affordability.

**On more capital.** Median return was flat to declining from $300 to $10,000.
$300 stays.

**On the strategy itself, measured over six years of real bars (2021–2026):**

- Chase +0.079R at **year-level t = +1.4**. Not significant. The pooled figure
  of t = 5.6 over 13,912 trades is *not usable* — trades inside one year share
  a market and are not independent draws.
- **2022 returned −0.168R at t = −4.9.** Which year you are in matters roughly
  four times more than the strategy does.
- The robust finding is structural: breakouts that never pull back return
  **+0.957R** (year-level t = 12.1, every year including 2022), and waiting for
  a pullback forfeits exactly those. No signal-time feature separates them —
  the best candidate moves the *label* by +0.40 and captures 35% of the return
  that implies, because within the group it reverses.

**On diversification.** There isn't any available. Minimum pairwise 60-day
correlation across a day's own signals was **0.45**, including a space company
against a semiconductor. A long-only breakout book is a single directional
bet, so the controls are a 4% book-wide open-risk cap and a size taper, not
name selection.

## Run it

```bash
python3 -m unittest discover -s tests -t . # 469 tests — the constitution's teeth
python3 -m sim.run_suite --seeds 300      # Monte Carlo the guardrails

python3 -m tools.preflight_phase2         # network, keys, model, tests, state, data
python3 -m tools.trading_day open         # reconcile, mark, halt check
python3 -m tools.trading_day preclose     # close the entry book before the bell
python3 -m tools.trading_day close        # report, overnight risk, escalations
python3 -m tools.trading_day week         # Phase 2 exit criteria

python3 -m tools.status                   # account detail
python3 -m tools.screen                   # today's breakouts, auditable
python3 -m tools.screen --build-universe  # rebuild data/universe.json
python3 -m tools.paper_session            # real data, real gate, no orders
python3 -m tools.paper_session --submit   # ...and actually send them
python3 -m tools.smoke_submit             # live order path, self-cleaning
python3 -m tools.model_check <task>       # model routing; exit 1 = do not proceed
python3 -m tools.model_check <task> --at-write   # re-check the floor AT a durable
                                          #   write — CLAUDE_EFFORT tracks the
                                          #   turn, so task-start clearance
                                          #   does not carry (T-10)
python3 -m tools.netcheck                 # are the data sources reachable AND usable?
python3 -m tools.review --week            # expectancy, win rate, costs
python3 -m tools.design_doc               # regenerate the design spreadsheet
```

Research tools, all against real bars:

```bash
python3 -m tools.pit_study --fetch        # cache 2,472 symbols, 2021-2026
python3 -m tools.multiyear                # entry study, every year, year-level stats
python3 -m tools.multiproxy               # six signal-time features, every year
python3 -m tools.entry_study --year 2026  # chase vs retest, one year
```

No third-party dependencies — standard library only.

## Layout

```
.claude/skills/   premarket-brief, news-intel, trade-plan,
                  execution, trade-journal, session-close
engine/           config (the constitution), risk, portfolio, broker, market,
                  sim, strategies, posture, feasibility, model_policy
adapters/         base + authorization gate, alpaca, robinhood_mcp preflight
tools/            the daily spine (trading_day, paper_session, screen),
                  controls (preflight_phase2, model_check, netcheck, status),
                  research (pit_study, multiyear, multiproxy, entry_study,
                  proxy_study, target_study), design_doc
sim/              Monte Carlo suite, capital sweep, universe, results
tests/            469 tests
data/             universe.json — the committed, reproducible screen input
state/            ledger, fills, plans, briefs, journal, reports, reviews,
                  authorizations.jsonl (every human override, dated and signed)
docs/             01-16 plus the generated design spreadsheet
```

## Honest limitations

- **One closed trade.** Execution past "the broker accepted it" has been
  exercised once, which is not enough to trust.
- **Nothing is significant yet.** Six years of bars put the edge at t ≈ 1.4.
  One closed trade puts the *live* edge at no measurement at all.
- **Survivorship bias remains.** The universe is built from the broker's asset
  list as it stands today, so names delisted before today are absent. Every
  backtested year is biased upward and the early years most.
- **Fractional shares cannot carry a bracket** at this broker, so whole-share
  sizing caps a single position near $75 at this account size.
- **The `.claude/settings.json` allowlist is a human decision.** The
  permission classifier blocks the agent from writing its own, correctly
  (`docs/11-autonomous-permissions.md`).
- **The gate is attributable, not enforceable.** Nothing in-process can
  establish that a human is present; `state/authorizations.jsonl` makes a false
  claim permanent and signed, which is a different thing from preventing it.
