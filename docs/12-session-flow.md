# Session flow — what happens at each firing

Four firings per trading day, each bounded by the mechanical spine. The rule
that shapes every diagram below: **the model decides what to trade, code
decides whether it is allowed.** Wherever a diamond is drawn, the test behind
it is deterministic code in `engine/`, not a judgement.

Rendered by GitHub directly. To regenerate the images:
`npx -y @mermaid-js/mermaid-cli -i docs/12-session-flow.md -o docs/flow.svg`

---

## 1. The day, end to end

```mermaid
flowchart TD
    A([Routine fires]) --> B[python3 -m tools.preflight_phase2]
    B -->|exit != 0| STOP1([DO NOT TRADE<br/>write the brief, say why])
    B -->|exit 0| C[python3 -m tools.trading_day open]
    C -->|reconcile fails<br/>or halt state| STOP1
    C -->|NORMAL| D[premarket-brief]

    D --> E[news-intel]
    E --> F[trade-plan]
    F --> G[execution<br/>tools.paper_session --submit]
    G --> H{{midday firing<br/>15:30 UTC-4}}
    H --> I[manage open positions<br/>refresh news, mark refusals]
    I --> J{{pre-close firing}}
    J --> K[trade-journal<br/>one entry per closed trade]
    K --> L[python3 -m tools.trading_day close]
    L --> M([report, overnight risk,<br/>escalations])

    style STOP1 fill:#f8cecc,stroke:#b85450
    style M fill:#d5e8d4,stroke:#82b366
```

---

## 2. The open firing, in detail

The only firing that may open new risk.

```mermaid
flowchart TD
    A([open firing]) --> B[preflight: network, keys,<br/>model, tests, state, data]
    B -->|fail| X([halt the day])
    B --> C[trading_day open:<br/>reconcile against the broker]
    C --> D{risk state<br/>== NORMAL?}
    D -->|DAY_HALT / WEEK_HALT| Y([manage positions only,<br/>write the brief, stop])
    D -->|LOCKED| Z([human only —<br/>RiskOfficer.unlock])
    D -->|NORMAL| E[premarket-brief:<br/>account, regime, news, calendar]

    E --> F[/posture: NORMAL,<br/>RISK_OFF or NO_TRADE/]
    F --> G[news-intel: two independent<br/>lanes, every claim sourced]
    G --> H[tools.screen against<br/>data/universe.json - 150 names]
    H --> I[trade-plan:<br/>fully-specified proposals]
    I --> J{plan written?}
    J -->|empty plan| K([deliberate NO-TRADE.<br/>The scanner is NOT consulted.])
    J -->|proposals| L[execution]

    style Z fill:#f8cecc,stroke:#b85450
    style Y fill:#ffe6cc,stroke:#d79b00
    style K fill:#dae8fc,stroke:#6c8ebf
```

---

## 3. The risk gate — every order passes through here

This is the part that may not be bypassed, reasoned around, or satisfied by
reshaping an order until it fits. A rejection is recorded and the session
moves on.

```mermaid
flowchart TD
    A[/OrderProposal/] --> B{side == buy?}
    B -->|sell| PASS([exits are always permitted])
    B -->|buy| C{state == NORMAL?}
    C -->|no| R1([REJECT: no new risk])
    C --> D{stop supplied<br/>and below entry?}
    D -->|no| R2([REJECT: no stop, no trade])
    D --> E{under the max<br/>concurrent positions?}
    E -->|no| R3([REJECT: at position cap])
    E --> F{asset class}

    F -->|option| G{equity >= $1,500<br/>AND 30 trades at >= +0.10R<br/>AND 7-45 DTE<br/>AND defined risk<br/>AND 15+ min since open}
    G -->|no| R4([REJECT: option sleeve locked])
    F -->|crypto| R5([REJECT in practice:<br/>broker attaches no stop])
    F -->|equity / etf| H
    G -->|yes| H

    H{target supplied?} -->|no| R6([REJECT: cannot grade R])
    H --> I{"expected R =<br/>(target-price)/(price-stop)<br/>>= 1.5?"}
    I -->|no| R7([REJECT: target too close<br/>for the stop taken])
    I --> J[size = min of:<br/>2% risk budget,<br/>single-position cap,<br/>class cap,<br/>settled cash after reserve]
    J --> K[round down to whole shares]
    K --> L{qty > 0?}
    L -->|no| R8([REJECT: names the<br/>binding constraint])
    L -->|yes| M([APPROVE with sized qty])

    style M fill:#d5e8d4,stroke:#82b366
    style PASS fill:#d5e8d4,stroke:#82b366
    style R1 fill:#f8cecc,stroke:#b85450
    style R2 fill:#f8cecc,stroke:#b85450
    style R3 fill:#f8cecc,stroke:#b85450
    style R4 fill:#f8cecc,stroke:#b85450
    style R5 fill:#f8cecc,stroke:#b85450
    style R6 fill:#f8cecc,stroke:#b85450
    style R7 fill:#f8cecc,stroke:#b85450
    style R8 fill:#f8cecc,stroke:#b85450
```

---

## 4. Submission and recording — submitting is not filling

The half that had never executed, and where two of the three critical bugs
found on 2026-09-18 were living.

```mermaid
flowchart TD
    A([APPROVED proposal]) --> B[build OrderTicket:<br/>bracket, GTC, stop + target]
    B --> C{dry run?}
    C -->|yes| D[write a tagged dry_run row.<br/>closed_trades drops it.]
    C -->|no| E[POST /v2/orders]
    E --> F[await_fill: poll to a<br/>terminal status, 30s]
    F --> G{filled_qty > 0<br/>AND a real price?}
    G -->|yes| H[append_fill at the BROKER's<br/>price and quantity;<br/>report slippage]
    G -->|rejected / cancelled| I([nothing recorded])
    G -->|still working| J[carry into<br/>ledger.working_orders;<br/>nothing recorded]
    H --> K{partial?}
    K -->|yes| J
    K -->|no| L([position open,<br/>stop resting GTC])

    style H fill:#d5e8d4,stroke:#82b366
    style L fill:#d5e8d4,stroke:#82b366
    style J fill:#ffe6cc,stroke:#d79b00
```

---

## 5. The close firing

```mermaid
flowchart TD
    A([close firing]) --> B[trading_day close:<br/>reconcile against the broker]
    B --> C[cancel_unfilled_entries<br/>parents only — never cancel_all]
    C --> D[re-read positions_without_stops<br/>AFTER cancelling]
    D --> E{any position<br/>without a stop?}
    E -->|yes| F([ESCALATE tonight —<br/>not tomorrow morning])
    E -->|no| G[price overnight risk:<br/>1x stops, and 2x gap through]
    G --> H{2x-gap loss ><br/>the 8% weekly halt?}
    H -->|yes| I([reduce overnight<br/>exposure now])
    H -->|no| J[write the session report;<br/>update the ledger]
    J --> K[trade-journal:<br/>one entry per closed trade]
    K --> L([commit and push —<br/>the container is reclaimed])

    style F fill:#f8cecc,stroke:#b85450
    style I fill:#ffe6cc,stroke:#d79b00
    style L fill:#d5e8d4,stroke:#82b366
```

---

## Why the diagrams stop where they do

Each one ends at a commit or a stop. That is deliberate: the container is
ephemeral and is reclaimed after the session, so anything not pushed to the
repository did not happen. `state/` is tracked in git for exactly this reason
— see `docs/04-lessons.md`, 2026-09-15, "The circuit breakers reset overnight
in the configuration we were about to run".
