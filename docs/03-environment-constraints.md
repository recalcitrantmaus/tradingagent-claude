# Environment and connectivity constraints

Findings from the build session, recorded because they change the deployment
plan rather than merely inconveniencing it.

## 1. This sandbox cannot reach any market data or broker host

Every candidate endpoint returns a **403 policy denial at the egress proxy**:

| Host | Result |
|---|---|
| `query1.finance.yahoo.com` | 403 CONNECT (policy denial) |
| `api.coingecko.com` | 403 CONNECT |
| `docs.robinhood.com` | 403 CONNECT |
| `www.alphavantage.co` | 403 CONNECT |
| `stooq.com` | 403 CONNECT |
| `robinhood.com` | blocked by the egress proxy |

Confirmed via `curl -sS "$HTTPS_PROXY/__agentproxy/status"`.

Consequences:

- **All simulation in this repo runs on the synthetic generator in
  `engine/market.py`.** No result here is a backtest against real history.
  The generator is deliberately hostile (regime switching, 2%/day jump
  probability, fat tails, correlated beta) but it is not the market.
- The agent's *live* information diet in this environment comes through
  `WebSearch` and `WebFetch`, which do work — but `WebFetch` is subject to
  the same domain policy, so some sources will be unavailable.
- **Live trading cannot run from this environment as configured.** Either
  the environment's network policy is widened to allow the broker and data
  hosts, or the agent runs somewhere else. This must be resolved before
  Phase 3.

## 2. Robinhood has no official retail API for stocks or options

- Robinhood publishes an **official Crypto Trading API only**
  ([docs.robinhood.com/crypto/trading](https://docs.robinhood.com/crypto/trading/),
  announced [May 30, 2024](https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/)).
  It is US-only, credentials are created in a desktop-browser portal, and
  requests are signed with `x-api-key`, `x-signature`, `x-timestamp` headers.
- For **equities and options there is no documented, supported public API.**
  The available paths are:
  1. **Manual execution.** The agent produces an order ticket; a human places
     it. Slow, but zero account-security and terms-of-service risk.
  2. **Unofficial clients** (e.g. `robin_stocks`), which drive Robinhood's
     private endpoints. These require full account credentials and MFA, can
     break without notice, and carry terms-of-service risk up to account
     restriction. **This is a decision for the account holder, in writing,
     not something the agent should adopt silently.**
  3. **A different broker for equities/options.** Alpaca and Tradier both
     publish documented trading APIs with paper-trading sandboxes. This is
     the recommended path for automated equity execution; Robinhood then
     carries the crypto sleeve via its official API.

The `execution` skill encodes this: dry-run by default, `--live` explicit,
and no unofficial path without a recorded human authorization.

## 3. Regulatory state is mid-transition — verify before Phase 3

Per [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
and FINRA's [April 2026 compliance summary](https://www.finra.org/compliance-tools/weekly-archive/04152026),
FINRA has adopted new intraday margin standards that **replace the day-trading
margin requirements, including the pattern-day-trader designation and the
$25,000 minimum equity requirement**. Effective date **June 4, 2026**, with
member firms permitted to phase in implementation until **October 20, 2027**.

The agent therefore does not know whether Robinhood currently applies the old
PDT regime or the new standard. `RiskConfig.assume_pdt_regime = True` models
the **stricter** case (3 day trades per 5 sessions). **Confirm Robinhood's
actual current treatment with the broker before live deployment** and set the
flag from fact, not from this note.

Cash accounts are not subject to the PDT rules but require settled funds
(T+1), which the ledger models via `Portfolio.settled_cash`.

## Sources

- [Robinhood Crypto Trading API docs](https://docs.robinhood.com/crypto/trading/)
- [Robinhood newsroom — Crypto Trading API, May 30, 2024](https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/)
- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
- [FINRA — new intraday margin standards](https://www.finra.org/compliance-tools/weekly-archive/04152026)
- [SEC — Margin Rules for Day Trading (PDF)](https://www.sec.gov/files/daytrading.pdf)
