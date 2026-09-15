---
name: execution
description: Place, manage and exit orders through the risk engine and the broker adapter, including stop placement, scale-outs, trailing and forced liquidation on a halt. Use when a trade plan exists and orders must actually be sent, or when open positions need intraday management. Trigger on "execute", "place the order", "manage positions", "exit", or any point where a decision becomes an order.
---

# Execution

The agent never sends an order directly. Every order goes through
`engine.risk.RiskOfficer.evaluate`, and the engine's `Decision` is final. If
the engine rejects a trade, the correct response is to record the rejection —
not to restructure the trade until it passes. Reshaping a trade to defeat a
guardrail is the failure mode this whole system exists to prevent.

## Order of operations, every session

1. **Reconcile.** Pull live positions and balances from the broker. If they
   disagree with `state/ledger.json`, stop and reconcile. Trading on a stale
   ledger is how a small loss becomes an unbounded one.
2. **Verify protective orders.** Every open position must have a live stop at
   the broker, not an intention in a file. A position without a resting stop
   is flattened, not held.
3. **Manage before you add.** Exits, scale-outs and trails come before any
   new entry.
4. **Enter.** Only proposals from today's plan, only after the engine
   approves.

## Entry mechanics

- Limit orders only. Market orders on a $300 account give away edge to the
  spread on every fill.
- No options in the first 15 minutes. Use the opening range to set the day's
  levels; the engine rejects earlier attempts.
- One entry per instrument per day. If the first entry stops out, the day is
  over for that name.
- After the fill, place the stop **immediately**, in the same breath. A stop
  you meant to place is not a stop.

## Exit mechanics

- **Stop.** Non-negotiable and never widened. Moving a stop away from price is
  prohibited; if you want to do it, you have already lost the trade and are
  now negotiating with it.
- **First target.** Sell half. Move the stop to breakeven. The remainder is
  now a free option on being right.
- **Trail.** After +1R, trail the remainder by 1.5 ATR (or 25% of premium for
  options).
- **Time stop.** If the catalyst window closes and the thesis has not paid,
  exit. Dead money is a position you cannot use.
- **Halt.** On `WEEK_HALT` or `LOCKED`, flatten everything at the next
  orderly opportunity. Do not wait for a better price.

## Broker adapter

Live trading uses `adapters/` (see `docs/03-environment-constraints.md` for
what is and is not available). Two hard rules:

- **Dry-run by default.** `--live` is an explicit flag, never a default, and
  the adapter refuses to send unless the config file records a human
  authorization string with today's date.
- **Robinhood has no official retail equities/options API.** Only crypto is
  officially supported. Equities and options require either manual execution
  from a generated order ticket or an unofficial client, which carries
  account-security and terms-of-service risk the human must accept in
  writing. Never silently take the unofficial path.

## Recording

Every order, fill, rejection and cancellation is appended to
`state/fills.jsonl` with the engine's stated reason. The journal skill reads
this. An unrecorded fill did not happen, and the next reconciliation will
treat it as a discrepancy.
