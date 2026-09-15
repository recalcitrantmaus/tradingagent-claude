---
name: news-intel
description: Gather and triage market-relevant news across the political spectrum plus crypto-native sources, with source links and a bias ledger. Use when building a pre-market brief, refreshing the feed intraday, or when a position moves unexpectedly and the cause is unknown. Trigger on "news", "what happened to X", "refresh the feed", "any headlines on", or before sizing up any position.
---

# News intelligence

The job is not to collect headlines. It is to find the small number of items
that change what a position is worth, and to be honest about who is telling
you.

## Coverage requirement

Sample across, and label each item with, its lane:

| Lane | Examples |
|---|---|
| Wire / market data | Reuters, AP, Bloomberg, CNBC, MarketWatch |
| Right-leaning | WSJ editorial, Fox Business, NY Post business |
| Left-leaning | NYT, Guardian business, MSNBC business |
| Financial trade | Barron's, FT, Investor's Business Daily |
| Primary source | SEC EDGAR filings, Fed statements, BLS/BEA releases, company IR |
| Crypto-native | CoinDesk, The Block, protocol blogs and governance forums |

**A claim is only actionable if it appears in a primary source or in at least
two lanes.** One outlet is a rumor. Several outlets in the same lane are one
outlet.

Primary sources outrank everything. A Fed statement beats ten takes on it.

## Crypto and social sources

Discord, Telegram and X are where crypto information moves first and where it
is least reliable. Treat them as a *lead generator only*: an item found there
is a prompt to go check a primary source (the protocol's own announcement,
an on-chain transaction, an exchange status page). **Never size a position on
an unverified social post.** Coordinated promotion is the base rate, not the
exception; if a thesis' only evidence is that people are excited, it is not a
thesis.

## Triage

For each candidate item ask, in order:
1. **Is it true?** Source, and a second one.
2. **Is it new?** Already-priced news is not an edge. If it is three days old
   and the chart already moved, it is history.
3. **What is the transmission mechanism?** Name the path from headline to the
   price of a specific instrument. If you cannot name it in one sentence,
   drop the item.
4. **What is the counter-case?** Who is on the other side of this trade and
   why are they not stupid?

Discard anything that fails 1-3. Record the answer to 4 with the trade.

## Cadence

- **Pre-open** — overnight tape, Asia and Europe, futures, any 8:30 ET print.
- **~10:00 ET** — after the opening auction settles.
- **Midday** — headline check only; do not re-litigate the thesis on noise.
- **Pre-close** — anything that changes overnight-hold risk.
- **Event-driven** — any open position moving more than 1.5x its ATR.

## Output

Append to `state/news/YYYY-MM-DD.md`, newest first:

```
HH:MM ET | lane | headline | URL | instrument affected | mechanism | confidence (primary/corroborated/single-source/rumor)
```

Never record an item without a URL. If a fetch was blocked, record the
attempt and the block — a blocked source is information about your own
coverage, and coverage gaps belong in the brief.
