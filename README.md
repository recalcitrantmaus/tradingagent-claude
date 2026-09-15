# tradingagent-claude

An autonomous trading agent for a small ($300) Robinhood account, built so
that the parts which can lose money are deterministic, tested code and the
parts which need judgment are LLM skills.

**Status: Phase 1 complete.** Skills written, risk engine built and tested,
3,600 simulated account-years run. Not connected to a broker. Not trading.

## Read these first

| Document | Why |
|---|---|
| [`docs/01-feasibility.md`](docs/01-feasibility.md) | What a $300 account can and cannot do, with the arithmetic |
| [`docs/05-sim-report.md`](docs/05-sim-report.md) | Phase 1 simulation report: what was tested, what broke, what changed |
| [`docs/06-model-strategy.md`](docs/06-model-strategy.md) | Which Claude model to run at which stage, and why |
| [`docs/02-architecture.md`](docs/02-architecture.md) | How the pieces fit |
| [`docs/03-environment-constraints.md`](docs/03-environment-constraints.md) | Network, broker API and regulatory constraints |
| [`docs/07-deployment.md`](docs/07-deployment.md) | Running it autonomously: network, model routing, broker, kill switches |
| [`docs/04-lessons.md`](docs/04-lessons.md) | Every rule, and the evidence behind it |
| [`CLAUDE.md`](CLAUDE.md) | The agent's own operating instructions |

## Headline findings

- The 5%/week target compounds to **+1,164% annualized**. Treated as a hurdle
  rate it is harmless; treated as a quota it is fatal.
- **Options are unaffordable at $300** (a 2% risk budget is $6; one contract
  with a policy stop risks ~$80) — **and unprofitable at every size tested.**
  A sweep from $300 to $10,000 found long-premium buying negative everywhere
  (-14% to -15% median at $2,500+) under every stop setting tried. So the
  sleeve is gated on *measured edge*, not on affordability.
- **More capital does not buy more edge.** Median return was flat to
  declining from $300 to $10,000. $300 stays.
- The chase-the-target control strategy hit the **-20% drawdown lock in 100%
  of 300 simulated years**, winning 3.2% of its trades.
- With guardrails removed, option trading on $300 **ruined 94% of accounts**
  (median final equity $18.02) — while hitting the +5% weekly target *more
  often* than the disciplined strategy. Optimizing the stated KPI selects for
  ruin.
- Position sizing does **not** change how often a week hits +5%. It only
  changes how much the losing weeks cost.

## Run it

```bash
python3 -m unittest discover -s tests            # 20 tests, the risk constitution
python3 -m sim.run_suite --seeds 300 --days 260  # Monte Carlo, default config
python3 -m sim.run_suite --seeds 300 --no-guardrails       # ablation
python3 -m sim.run_suite --seeds 300 --options-at-300      # isolate the option floor
python3 -m tools.status                          # account state
python3 -m sim.capital_sweep                     # does more capital help?
python3 -m tools.review --week                   # expectancy, win rate, costs
python3 -m tools.model_check                     # model routing policy
python3 -m tools.paper_session --dry-run         # real data, real gate, no orders
```

No third-party dependencies — standard library only.

## Layout

```
.claude/skills/   premarket-brief, news-intel, trade-plan,
                  execution, trade-journal, session-close
engine/           config (the constitution), risk, portfolio, broker,
                  market, sim, strategies, feasibility, model_policy
adapters/         base + authorization gate, alpaca, robinhood_mcp preflight
tools/            status, review, model_check, paper_session, ledger state
sim/              Monte Carlo suite, capital sweep, universe, results
tests/            38 tests — the constitution's teeth
docs/             feasibility, architecture, constraints, lessons,
                  sim report, model strategy, deployment
```

## Not yet done

- No real market data anywhere in this repo — every number is synthetic.
- Alpaca and Robinhood-MCP adapters are built and tested, but **every broker
  and data host is blocked by this environment's network policy** — the
  adapters cannot be exercised against a real endpoint from here.
- No live orders. No real fills of any kind.
- No measurement of whether *model-generated* theses have positive
  expectancy. That is Phase 2, and it is the question that decides everything.
