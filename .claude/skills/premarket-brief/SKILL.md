---
name: premarket-brief
description: Build the pre-market intelligence brief before any trading decision. Use at the start of every trading day, or whenever the agent is about to place its first order of a session. Pulls rolling 90-day and 1-year market structure, overnight news, crypto flow, the economic calendar, and the account's own state, then emits a dated brief the trade-plan skill consumes. Trigger on "premarket", "start the trading day", "what's the setup today", or any request to trade when no brief exists for today.
---

# Pre-market brief

No order is placed on a day without a brief dated that day. If a brief is
missing or older than the current session, build one first. Refusing to trade
is always an acceptable output.

## 1. Account state first (always, before any market view)

Read `state/ledger.json` and run:

```
python3 -m tools.status
```

Record: equity, settled cash, open positions with their stops, current risk
state (`NORMAL` / `DAY_HALT` / `WEEK_HALT` / `LOCKED`), week-to-date P&L,
drawdown from peak, and day-trades used in the last 5 sessions.

**If the state is not `NORMAL`, stop here.** Write the brief, note the halt,
and manage existing positions only. A halted account does not get a market
opinion; it gets a review.

## 2. Market structure (the slow layer)

Two horizons, because they answer different questions:

- **Rolling 1 year** — what regime are we in? Trend of the broad index, the
  200-day, breadth, rate direction, dollar, credit spreads, VIX term
  structure. This sets *how aggressive the day may be*, not what to buy.
- **Rolling 90 days** — what is working *now*? Sector leadership and
  laggards, factor rotation (growth/value, large/small), correlation between
  equities and crypto, realized vs. implied vol.

Write both as one sentence each. If you cannot write the sentence, you do not
understand the regime, and position size stays at half.

Pull the rate, spread and vol inputs from `adapters.fred` rather than from a
headline — each reading arrives with its observation date:

```
python3 -c "from adapters.fred import snapshot; import json; print(json.dumps(snapshot(), indent=2))"
```

`DGS10`, `T10Y2Y`, `BAMLH0A0HYM2`, `VIXCLS`, `ICSA`, `CPIAUCSL`, `UNRATE`.
Quote the `as_of` date alongside any value you use. If `stale_days` is large
for a series you are leaning on, say so — a number is only as current as its
observation date, not as the moment you fetched it.

**Then run the screen before forming any view on whether there is a setup:**

```
python3 -m tools.screen
```

It reads the committed universe in `data/universe.json`. On 2026-09-16 and
09-17 this skill twice concluded "no setup" from a hand-built list of names,
while the committed screen found six breakouts. The measured base rate is that
**59 of 60 sessions carry at least one**, so an empty screen is a two-percent
event: treat it as a reason to suspect the instrument, not as a finding about
the market. If you disagree with the universe, recommend a change to
`CRITERIA` in `tools/screen.py` — do not quietly substitute a list of your own,
because a screen that lives only in a session cannot be checked by anyone.

## 3. News (the fast layer)

Delegate to the `news-intel` skill. Require it to return sources, not
summaries you cannot trace. Carry forward only items with a plausible
transmission mechanism to a position you might take today.

## 4. Calendar

CPI/PPI/PCE, FOMC and Fed speakers, jobs prints, Treasury auctions, earnings
for anything in the watchlist, options expiry, crypto unlocks and protocol
upgrades. **A scheduled binary event inside a position's holding window is a
reason not to take the position**, unless the trade *is* the event and it is
sized as a defined-risk lottery within the 2% budget.

## 5. Output

Write `state/briefs/YYYY-MM-DD.md`:

```markdown
# Pre-market brief — YYYY-MM-DD
## Account
equity / settled cash / risk state / open positions / WTD P&L / drawdown / day trades used
## Regime (1y)
one sentence + the evidence
## What's working (90d)
one sentence + the evidence
## Overnight news that matters
- item — source URL — why it moves something I might own
## Calendar today
## Posture
RISK_ON | NEUTRAL | RISK_OFF | NO_TRADE  + the single reason
## Watchlist
ticker — setup — trigger — invalidation
```

`Posture` is binding. `RISK_OFF` caps new risk at 1% per trade and one
position. `NO_TRADE` means no entries at all.

## Honesty rules

- Cite a URL for every factual claim about the world. Never invent a source,
  a price, or a statistic. If you could not retrieve data, write
  "unavailable" and downgrade posture — do not fill the gap from memory.
- Prices from memory are stale by definition. Anything you did not retrieve
  today is not a price, it is a guess.
- Note explicitly when the network blocked a source. A brief built on three
  blocked sources is a `NO_TRADE` brief.
