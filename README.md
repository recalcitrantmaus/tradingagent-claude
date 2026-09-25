# tradingagent-claude

An autonomous trading agent for a small ($300) account, built so that the
parts which can lose money are deterministic, tested code and the parts which
need judgment are LLM skills.

**One rule outranks everything: the model decides what to trade; code decides
whether it is allowed.** If `RiskOfficer.evaluate` rejects an order, the
correct action is to record the rejection and move on — never to reshape the
order until it passes. That behaviour is the failure mode this whole system
exists to prevent.

## Status — Phase 2, day 3 of live paper trading

| | |
|---|---|
| Account | $300 Alpaca **paper**, equity $299.99, flat, risk state NORMAL |
| Sessions run | 7, autonomously, on a scheduled Routine |
| Orders placed | yes — bracket orders accepted by the broker, plus smoke tests |
| **Fills** | **zero, ever** |
| Tests | 206 |
| Simulation | 300-seed Monte Carlo per arm; sweeps up to 3,000 seeds |
| Network | open since 2026-09-15 |
| Live market data | yes — 2,472 symbols, daily bars 2021–2026, consolidated tape |

**The headline number is the zero.** Three days of autonomous sessions have
produced no fills, so the paths that record a fill, promote a bracket leg from
`held` to `new`, and cancel resting entries before the close are all still
unverified against reality. A flat account is an absence of evidence, not
evidence that the guardrails work — `trading_day week` now says so explicitly
rather than printing `[ok]` on criteria nothing has tested.

**New session? Start with [`HANDOFF.md`](HANDOFF.md), then `CLAUDE.md`.**

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
python3 -m unittest discover -s tests -t . # 426 tests — the constitution's teeth
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
tests/            206 tests
data/             universe.json — the committed, reproducible screen input
state/            ledger, fills, plans, briefs, journal, reports, reviews,
                  authorizations.jsonl (every human override, dated and signed)
docs/             01-16 plus the generated design spreadsheet
```

## Honest limitations

- **Zero fills.** Everything about execution past "the broker accepted it" is
  untested against reality.
- **Nothing is significant yet.** Six years of bars put the edge at t ≈ 1.4.
  Zero closed trades put the *live* edge at no measurement at all.
- **Survivorship bias remains.** The universe is built from the broker's asset
  list as it stands today, so names delisted before today are absent. Every
  backtested year is biased upward and the early years most.
- **Fractional shares cannot carry a bracket** at this broker, so whole-share
  sizing caps a single position near $75 at this account size.
- **A `.claude/settings.json` allowlist is still missing** — the permission
  classifier blocks the agent from writing it, correctly. A human must install
  it (`docs/11-autonomous-permissions.md`).
- **The gate is attributable, not enforceable.** Nothing in-process can
  establish that a human is present; `state/authorizations.jsonl` makes a false
  claim permanent and signed, which is a different thing from preventing it.
