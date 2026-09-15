# Deployment: running the agent autonomously

Three things have to be true before the agent runs unattended: it reaches
market data and a broker, it runs each task on a cleared model, and a human
can stop it instantly.

## 1. Network

Nothing in Phase 2 or 3 works from the environment this was built in — every
data vendor and broker host is denied at the egress proxy
(`docs/03-environment-constraints.md`). Fix this first, by widening the
environment's network policy to the hosts below or by running elsewhere.

| Purpose | Hosts |
|---|---|
| Alpaca paper trading | `paper-api.alpaca.markets`, `data.alpaca.markets` |
| Alpaca live | `api.alpaca.markets` |
| Robinhood agentic MCP | `agent.robinhood.com` |
| News and research | already available via `WebSearch` |

Verify with `curl -sS "$HTTPS_PROXY/__agentproxy/status"` — it names the
hosts that were refused and why.

## 2. Model routing

The agent cannot choose its own model — whatever launches the session sets it.
So routing is enforced in two places:

**a. The Routine that launches each session** sets the model. Use two
Routines, not one:

| Routine | Schedule (ET) | Model | Effort | Prompt |
|---|---|---|---|---|
| Daily trading loop | weekdays 08:30 | `claude-sonnet-5` | `xhigh` | Run the premarket-brief skill, then trade-plan, then execution. Close with session-close. |
| Weekly review | Fridays 16:30 | `claude-opus-5` | `xhigh` | Run the weekly review in the trade-journal skill. Promote or delete rules per docs/04-lessons.md. |

Set `TRADING_AGENT_MODEL` and `TRADING_AGENT_EFFORT` as environment variables
in each environment so the agent can see what it is running on.

**b. The agent checks itself** before durable tasks:

```
python3 -m tools.model_check weekly-review   # exit 1 = do not proceed
python3 -m tools.model_check                 # print the whole policy
```

Rule-promotion, weekly review, post-halt review and unlock authorization
**block** below Opus tier. The routine loop warns and continues — the risk
engine is the safety net there, not the model.

## 3. Broker

### Option A — Alpaca paper (recommended for Phase 2)

Free paper keys at https://app.alpaca.markets/. Documented REST API, a paper
endpoint that behaves like the live one, and market data included, which is
why it is the right substrate for measuring expectancy.

```bash
export ALPACA_API_KEY_ID=...        # paper keys; never commit these
export ALPACA_API_SECRET_KEY=...
python3 -m tools.paper_session --dry-run     # reads real data, sends nothing
python3 -m tools.paper_session --submit      # sends to the PAPER endpoint
```

`--dry-run` is the default. `AlpacaAdapter(live=True)` additionally requires
`confirm_live=True` at the call site **and** a same-day
`state/authorization.json`.

### Option B — Robinhood agentic MCP (Phase 3)

Robinhood's [Agentic Trading](https://robinhood.com/us/en/agentic-trading/)
connects Claude Code to a dedicated agentic account over MCP. Add to
`.mcp.json` (see `examples/mcp.json.example`):

```json
{ "mcpServers": { "robinhood-trading": { "type": "http", "url": "https://agent.robinhood.com/mcp/trading" } } }
```

Before the first order, in the Robinhood app:

1. A **dedicated agentic account** — never the main one.
2. Pre-load exactly $300. This is the hardest limit in the system: the only
   one the agent cannot reason its way around.
3. Spending controls at or below the agent's own risk policy.
4. **Order previews ON** for the first live week. Robinhood previews by
   default but will place without confirmation if the agent has been told to
   act without asking — that switch is yours, not the agent's.
5. Find the instant-disable control before you need it.

Then, before every order tool call, `adapters/robinhood_mcp.preflight()` must
pass: risk state `NORMAL`, ledger reconciled today, every position carrying a
resting stop, the risk engine's approval, and a valid authorization.

## 4. The stop-everything controls

| Control | Where | Effect |
|---|---|---|
| Instant agent disable | Robinhood app | Agent loses order authority immediately |
| Pre-loaded balance | Robinhood app | Caps total possible loss, unconditionally |
| `risk_state: LOCKED` | `state/ledger.json` | Agent refuses all new risk until a human calls `unlock()` |
| Delete the Routine | claude.ai Routines | Agent stops waking up |
| Revoke broker keys | Alpaca dashboard | Adapter cannot authenticate |

Know all five. The first two are outside this repo, which is exactly why they
are the ones to rely on.

## 5. Phase 2 exit criteria

Do not proceed to live trading on the strength of a good week. Require:

- [ ] **30+ closed paper trades** — fewer is noise, not evidence
- [ ] **Positive measured expectancy** (`python3 -m tools.review`)
- [ ] **Zero guardrail breaches** — no unstopped position, no order that
      bypassed the gate, no unreconciled session
- [ ] **Costs below realized gains** — the most likely quiet failure
- [ ] **Every thesis traceable to a source URL** in the journal
- [ ] **The same model configuration you intend to run live**

Note what is *not* on that list: hitting 5% in any week.
