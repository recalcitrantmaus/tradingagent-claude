---
name: session-close
description: End-of-day shutdown - reconcile the ledger against the broker, verify every open position has a live protective stop, mark the equity curve, run circuit-breaker checks and write the daily report. Use at every market close and before the agent goes idle with positions open. Trigger on "close out the day", "end of session", "daily report", or any point the agent stops monitoring while holding risk.
---

# Session close

The agent is most dangerous when it stops paying attention while holding
risk. This routine makes going idle safe.

## Checklist (all of it, every day)

1. **Reconcile.** Broker positions and cash vs. `state/ledger.json`. Any
   discrepancy is a stop-everything event: do not trade tomorrow on an
   unreconciled ledger.
2. **Protective orders.** Every open position has a resting stop at the
   broker, good-til-cancelled, at or inside the policy stop. Crypto included
   — it trades all night and will not wait for the agent to wake up.
3. **Overnight risk.** Sum the loss if every open position gapped to its
   stop, plus the loss if they gapped 2x through it (stops do not hold
   through gaps). If the 2x figure exceeds the weekly halt threshold, reduce
   overnight exposure now.
4. **Mark.** Append today's closing equity to the curve. Recompute drawdown
   from peak and the circuit-breaker state.
5. **Journal.** One entry per position closed today.
6. **Report.** Write `state/reports/YYYY-MM-DD.md`.
7. **Tomorrow.** Note the levels that would trigger action, the calendar, and
   any position approaching a time stop.

## Daily report

```markdown
# Session report — YYYY-MM-DD
Equity: $X (day X%, week X%, since inception X%)
Risk state: NORMAL | DAY_HALT | WEEK_HALT | LOCKED
Drawdown from peak: X%
Trades: N closed (W win / L loss), realized $X, costs $X
Open overnight: ticker / size / stop / risk-if-stopped / risk-if-2x-gap
Lessons: ...
Tomorrow: ...
```

## Escalate to the human, same day, when any of these is true

- Risk state is `LOCKED` (only a human can clear it).
- The ledger did not reconcile.
- A stop failed to execute or was filled far through its level.
- Realized weekly loss exceeds 8%.
- Measured edge over the last 20 trades is negative.
- A data source the strategy depends on has been unavailable for two sessions.

Escalation is a plain statement of what happened, what it cost, and what you
propose — not a reassurance.
