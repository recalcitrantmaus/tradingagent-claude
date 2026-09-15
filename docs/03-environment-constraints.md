# Environment and connectivity constraints

Findings from the build session, recorded because they change the deployment
plan rather than merely inconveniencing it.

## 1. RESOLVED 2026-09-15 — network access is open

The environment's network access was changed from **Trusted** to **Custom**
with the allowlist in `docs/08-network-policy.md`. All required and primary
hosts now answer; verified with `python3 -m tools.netcheck --all`. The change
applied to the already-running session, so no restart was needed.

Real data confirmed flowing: 501 daily bars each for SPY, F and SOFI through
2026-09-15, with ATR/SMA/RSI/realized-vol computing off them, plus live BTC
and ETH prices from CoinGecko.

One genuine false positive found in the process: **`stooq.com` returns HTTP
200 with a JavaScript proof-of-work bot challenge rather than data.** It is
reachable and unusable. `tools/netcheck.py` now inspects response bodies and
reports that case as DEGRADED, because an allowlist entry that looks like it
works is worse than one that is plainly blocked.

### The original finding, for the record

Before the change, every candidate endpoint returned a **403 policy denial at
the egress proxy**:

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

## 2. CORRECTION — Robinhood does support agentic trading (since 2026-05-27)

**My Phase 1 report said Robinhood had no official path for automated equities
and options trading. That was wrong, and the correction changes the deployment
plan for the better.**

Robinhood launched [Agentic Trading](https://robinhood.com/us/en/agentic-trading/)
on 2026-05-27. It is not a REST API — it is an **MCP server** the agent
connects to directly at `https://agent.robinhood.com/mcp/trading`, and Claude
Code is a supported client. From Robinhood's published material and press
coverage:

| | |
|---|---|
| Asset classes | Long equities, options, and crypto |
| Account model | A **dedicated agentic account** with a pre-loaded balance; order authority does not extend beyond it |
| Approval | Orders are previewed for confirmation by default, **but the agent can place trades without confirmation if you have told it to act without asking** |
| Controls | Spending controls, limited account access, instant agent disable, fraud detection, manual approvals |

Three consequences for this build:

1. **The unofficial-client problem is gone.** No `robin_stocks`, no
   credential sharing, no terms-of-service risk. This is the supported path.
2. **The pre-loaded agentic account is the best guardrail in the system** —
   better than anything in `engine/risk.py`, because it is the one limit the
   agent genuinely cannot reason its way around. Fund it with exactly $300.
3. **The confirmation setting is the most consequential switch in the whole
   project.** It is the line between a supervised and an unsupervised agent,
   and it belongs to the account holder. `adapters/robinhood_mcp.py` holds
   the preflight that must pass before any order tool is called; Robinhood's
   controls are a second, independent layer. Configure both.

**Still to verify in the app before Phase 3** (this sandbox cannot reach
robinhood.com, so all of the above comes from search results, not from the
live product): the current MCP tool surface, which asset classes are enabled
on your account, the approval setting, and where the instant-disable control
is.

## 2b. Alpaca is blocked here too — the adapter does not fix the data problem

`adapters/alpaca.py` is built and tested, and Alpaca remains the right
paper-trading substrate. But it does not solve this environment's problem:

| Host | Result |
|---|---|
| `paper-api.alpaca.markets` | 403 CONNECT (policy denial) |
| `data.alpaca.markets` | 403 CONNECT |
| `api.alpaca.markets` | 403 CONNECT |
| `api.tradier.com` | 403 CONNECT |
| `agent.robinhood.com` | 403 CONNECT |

**The blocker is the environment's network policy, not the broker.** Every
candidate — data vendor, paper broker, live broker — is denied at the egress
proxy. Phase 2 needs one of:

- the environment's network policy widened to allow the chosen data and
  broker hosts (see https://code.claude.com/docs/en/claude-code-on-the-web
  for how environments are configured), or
- the agent running somewhere with ordinary outbound HTTPS.

`WebSearch` does work, and `WebFetch` works for domains the policy permits —
so the *news and research* half of the agent can function here. Only priced
market data and order routing cannot.

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

- [Robinhood Agentic Trading](https://robinhood.com/us/en/agentic-trading/)
- [Robinhood — Agentic Trading overview](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
- [Robinhood — Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
- [Robinhood newsroom — Robinhood is Now Open to Agents](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/)
- [TechCrunch — Robinhood now lets your AI agents trade stocks (2026-05-27)](https://techcrunch.com/2026/05/27/robinhood-now-lets-your-ai-agents-trade-stocks/)
- [Alpaca API documentation](https://docs.alpaca.markets/)
- [Robinhood Crypto Trading API docs](https://docs.robinhood.com/crypto/trading/)
- [Robinhood newsroom — Crypto Trading API, May 30, 2024](https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/)
- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
- [FINRA — new intraday margin standards](https://www.finra.org/compliance-tools/weekly-archive/04152026)
- [SEC — Margin Rules for Day Trading (PDF)](https://www.sec.gov/files/daytrading.pdf)
