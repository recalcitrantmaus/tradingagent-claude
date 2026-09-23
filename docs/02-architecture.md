# Architecture

One organizing principle: **the model decides what to trade; code decides
whether it is allowed.**

An LLM can be argued out of a rule — by a persuasive headline, by a losing
streak, by its own fluency. So every rule that protects capital lives in
`engine/`, is deterministic, and is pinned by a test. The skills in
`.claude/skills/` hold judgment: regime reading, news triage, thesis
construction, reflection. They propose. They never execute.

```mermaid
flowchart TD
    subgraph judgment["judgment — .claude/skills/ (LLM, may be argued with)"]
        N[news &amp; research<br/>WebSearch, WebFetch] --> PB[premarket-brief]
        PB --> NI[news-intel]
        NI --> TP[trade-plan]
    end

    TP -->|OrderProposal| GATE

    subgraph code["code — engine/ (deterministic, tested, cannot be argued with)"]
        GATE[["engine/risk.py<br/>RiskOfficer.evaluate"]]
    end

    GATE -->|"Decision(approved=False, reasons)"| REC[record the rejection<br/>and move on]
    GATE -->|"Decision(approved=True, qty)"| EX[execution skill]
    EX --> BR[engine/broker.py] --> AD[adapters/] --> BK[(broker)]
    BK --> PF[engine/portfolio.py<br/>the ledger]
    PF --> JR[trade-journal<br/>session-close]

    style GATE fill:#dae8fc,stroke:#6c8ebf,stroke-width:3px
    style REC fill:#f8cecc,stroke:#b85450
    style BK fill:#d5e8d4,stroke:#82b366
```

The only path from judgment to a broker runs through one function. There is no
second route, and `RiskOfficer.evaluate` cannot be reached with a proposal it
has not scored. **A rejection is an outcome, not an obstacle** — the correct
response is the left-hand branch, never reshaping the order until it passes.

## Modules

| Path | Responsibility |
|---|---|
| `engine/config.py` | The constitution. Every limit, as data. Changing it is a reviewed act. |
| `engine/risk.py` | The gate. Sizes or rejects every entry; runs the halt state machine. |
| `engine/portfolio.py` | Ledger: cash, positions, realized P&L, T+1 settlement, drawdown. |
| `engine/broker.py` | Paper fills with spread, slippage and fees. |
| `engine/market.py` | Indicators, Black-Scholes, CSV loader, synthetic generator. |
| `engine/sim.py` | Daily-bar simulation with no look-ahead and pessimistic intrabar ordering. |
| `engine/strategies.py` | Mechanical baselines for stressing the engine. Not the live brain. |
| `engine/feasibility.py` | Monte Carlo on the target and on edge sensitivity. |
| `tools/status.py` | Account state. Run before forming any opinion. |
| `tools/review.py` | Expectancy, win rate, profit factor, cost ratio. |
| `sim/run_suite.py` | The Monte Carlo suite and its ablations. |
| `tests/` | The constitution's teeth. |

## The state machine

```mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> DAY_HALT: −4% on the day<br/>or 4 straight losses
    DAY_HALT --> NORMAL: next session
    NORMAL --> WEEK_HALT: −8% on the week
    WEEK_HALT --> NORMAL: next Monday
    NORMAL --> LOCKED: −20% from peak
    DAY_HALT --> LOCKED: −20% from peak
    WEEK_HALT --> LOCKED: −20% from peak
    LOCKED --> NORMAL: RiskOfficer.unlock(authorization)<br/><b>human only</b>

    note right of DAY_HALT
        Stops NEW risk.
        Open positions are still managed.
    end note
    note right of WEEK_HALT
        Stops new risk AND flattens.
    end note
    note right of LOCKED
        Flattens. Needs a non-empty human
        note, recorded verbatim. The agent
        cannot clear it.
    end note
```

`DAY_HALT` and `WEEK_HALT` stop new risk; open positions are still managed.
`WEEK_HALT` and `LOCKED` additionally flatten. `LOCKED` requires
`RiskOfficer.unlock(authorization)` with a non-empty human note, recorded
verbatim — the agent cannot clear it.

Exits are approved unconditionally in every state. A risk system that can
block you from closing a position is a risk system that has become the risk.

## What the gate actually checks, in order

Every constraint below is a line in `engine/config.py` with a test behind it.
The order matters: an order refused early is never sized, so the reason given
is the *first* thing that stopped it, not the worst.

```mermaid
flowchart TD
    P[OrderProposal] --> S{side == sell?}
    S -->|yes| OK1([approved — exits are<br/>ALWAYS permitted])
    S -->|no| ST{risk state<br/>NORMAL?}
    ST -->|DAY_HALT / WEEK_HALT / LOCKED| NO1([refused])
    ST -->|yes| C{"len(positions) &lt;<br/>max_concurrent (4)?"}
    C -->|no| NO2([refused: at max positions])
    C -->|yes| R{"expected R ≥ 1.5?"}
    R -->|no| NO3([refused: target too close<br/>for the stop being taken])
    R -->|yes| SZ[size it — the SMALLEST of:]
    SZ --> Q1[2% risk budget,<br/>tapered ×0.5 per open position]
    SZ --> Q2[25% single-position cap]
    SZ --> Q3[90% asset-class cap]
    SZ --> Q4[settled cash − 10% reserve]
    SZ --> Q5[4% book open-risk cap<br/>− risk already on]
    Q1 & Q2 & Q3 & Q4 & Q5 --> W[round DOWN to whole shares]
    W --> Z{qty &gt; 0?}
    Z -->|no| NO4([refused: names the<br/>binding constraint])
    Z -->|yes| OK2([approved])

    style OK1 fill:#d5e8d4,stroke:#82b366
    style OK2 fill:#d5e8d4,stroke:#82b366
    style NO1 fill:#f8cecc,stroke:#b85450
    style NO2 fill:#f8cecc,stroke:#b85450
    style NO3 fill:#f8cecc,stroke:#b85450
    style NO4 fill:#f8cecc,stroke:#b85450
```

Whole-share rounding is the last step and it bites hardest at $300: a tapered
budget that buys 0.4 shares buys none. That is why a refusal names its binding
constraint — "size rounds to zero" alone would send the next session hunting
for a bug that is not there.

## Why the limits are what they are

| Limit | Value | Reason |
|---|---|---|
| Risk per trade | 2% | At $300 that is $6 — small enough that 20 consecutive losses do not end the account |
| Single position | 25% equity | One bad name cannot be the whole story |
| Option position | 15% equity | Premium can go to zero; equity rarely does |
| Crypto aggregate | 20% | 24/7 gap risk while the agent is asleep |
| Concurrent positions | 4 | $300 cannot supervise more, and correlation makes 8 positions one position |
| Cash reserve | 10% | Never fully invested; leaves room to manage |
| Day halt | -4% | Two full stops is a bad read, not bad luck |
| Week halt | -8% | Recoverable; -8% needs +8.7% to get back |
| Drawdown lock | -20% | -20% needs +25% to recover; beyond this, recovery math turns against you fast |
| Option min DTE | 7 | 0DTE is a coin flip with a spread on it |
| Option min equity | $1,500 | Derived in simulation — see `docs/05-sim-report.md` Result 2 |

## Adding a rule

A rule enters the system only with evidence (see the `trade-journal` skill):
five consistent closed trades, or a backtest showing improved median outcome
without a worse ruin rate. Then it goes in `engine/config.py` **and** gets a
test, and the evidence goes in `docs/04-lessons.md`. Rules without an
evidence trail are deleted at the next review.
