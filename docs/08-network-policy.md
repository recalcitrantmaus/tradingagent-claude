# Fixing the network policy

**Status: done, 2026-09-15.** Environment **Default**
(`env_016PcaV3rSbpLGpMNDS5GYLM`) moved from **Trusted** to **Custom** with the
allowlist below. All required and primary hosts verified reachable, and real
market data is flowing. The change took effect in the already-running session
— no restart was needed, contrary to what this document originally said.

Re-verify any time with `python3 -m tools.netcheck`. The rest of this page is
the procedure, kept for when the list needs extending or a new environment
needs the same treatment.

## Choose a level first

The environment dialog offers four levels: **None**, **Trusted**, **Full**,
**Custom**.

**Recommendation: Custom, not Full.** Full is one click and would work. The
reason not to take it is specific to this agent rather than general caution:

- It reads **adversarial content by design** — news sites, crypto Discord and
  social posts are inputs to `news-intel`, and some of that content is written
  by people who would like an agent to act on it.
- It will hold **order authority** over a real account.

An agent with both properties and unrestricted egress has an exfiltration path
and a wide blast radius if a page ever talks it into something. A Custom
allowlist means a page it fetches cannot direct it anywhere the list does not
already contain. The cost is maintaining a list; `tools/netcheck.py` prints it.

Use **Full** only if you would rather not maintain the list and accept that
trade-off knowingly. Do not use Full and live order authority together.

## The change

1. Go to **claude.ai/code**.
2. Select the **cloud icon** showing the environment name, in the row above
   the message box. (There is no settings page or direct URL for this.)
3. Hover **Default**, select the **settings gear** on the right.
4. Set **Network access** to **Custom**.
5. Paste the list below into **Allowed domains**, one per line.
6. **Keep "Also include default list of common package managers" CHECKED.**
   Unchecked means only your list is allowed, and `pip`, `npm` and the GitHub
   raw host stop working.
7. **Save changes.**
8. **Start a new session.** A running session keeps the policy it started
   with — this one will still be blocked after you save.

Generate the list with:

```
python3 -m tools.netcheck --domains
```

```text
paper-api.alpaca.markets
data.alpaca.markets
api.alpaca.markets
agent.robinhood.com
www.sec.gov
www.federalreserve.gov
www.bls.gov
www.bea.gov
home.treasury.gov
www.finra.org
api.coingecko.com
stooq.com
query1.finance.yahoo.com
docs.robinhood.com
www.reuters.com
apnews.com
www.cnbc.com
www.marketwatch.com
www.coindesk.com
www.theblock.co
```

A leading `*.` matches every subdomain, so `*.alpaca.markets` would replace
the first three lines. The explicit form is listed because it is easier to
audit later — you can see exactly which Alpaca surfaces the agent uses.

## Why each group is there

| Group | Hosts | Without it |
|---|---|---|
| Broker | `*.alpaca.markets`, `agent.robinhood.com` | No orders, no account state, no reconciliation |
| Market data | `data.alpaca.markets`, `stooq.com`, `query1.finance.yahoo.com`, `api.coingecko.com` | No prices. Every technical signal is dead |
| **Primary sources** | `sec.gov`, `federalreserve.gov`, `bls.gov`, `bea.gov`, `treasury.gov`, `finra.org` | `news-intel` ranks primary sources above every outlet; without them the agent can only read commentary about facts it cannot check |
| News | Reuters, AP, CNBC, MarketWatch, CoinDesk, The Block | `WebSearch` still works (it does not use this allowlist), but `WebFetch` on a specific article does not |

The primary-source group is the one I would not cut. A Fed statement beats
ten takes on it, and those domains are stable, public and cheap to allow.

## Verify

```
python3 -m tools.netcheck          # required + primary
python3 -m tools.netcheck --all    # plus optional data and news
```

It distinguishes three states, not two:

- **ok** — the host answered with data. An HTTP 401/403 **from Alpaca** counts:
  the network is open and only the key is missing, which is the next problem.
- **DEGRADED** — HTTP 200, but the body is a JavaScript bot challenge rather
  than data. `stooq.com` does this. Reachable and useless; treat as
  unavailable.
- **FAIL** — the egress proxy refused the CONNECT. This is what an allowlist
  gap looks like.

## Broker credentials — do not put live keys in environment variables

The environment dialog's **Environment variables** box is fine for paper keys
and wrong for live ones: **anyone who uses the environment can read the
values**, and the dialog says so.

**Paper trading (Phase 2).** Environment variables are acceptable. Paper keys
control nothing.

```
ALPACA_API_KEY_ID=...
ALPACA_API_SECRET_KEY=...
TRADING_AGENT_MODEL=claude-sonnet-5
TRADING_AGENT_EFFORT=xhigh
```

**Live trading (Phase 3).** On Pro and Max plans, use **API credentials**
instead (in the environment dialog, below Environment variables, when editing
an environment that already exists). The agent proxy attaches the key to
requests *after they leave the VM* — the key never reaches Claude, the
commands it runs, or the session's environment variables. Adding a credential
also makes its hosts reachable regardless of the access level.

One thing to check when you get there: **Alpaca authenticates with two custom
headers** (`APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`), and the credential
form is documented around a single header row. If it will not take both,
either use an Alpaca OAuth bearer token (one `Authorization: Bearer` header,
which the form is built for) or keep live trading off Alpaca and route it
through the Robinhood MCP path, where Robinhood holds the credentials and the
pre-funded agentic account is the real limit anyway. Do not fall back to
putting live secret keys in the environment variables box.

API credentials are not available on Team or Enterprise plans yet.

## Also set, while you are in the dialog

```
TRADING_AGENT_MODEL=claude-sonnet-5
TRADING_AGENT_EFFORT=xhigh
```

`tools/model_check.py` reads these to enforce the routing rules in
`docs/07-deployment.md`. Without them it cannot verify the running model, and
blocking tasks (rule promotion, weekly review) will refuse to run — which is
the correct failure direction, but an annoying one to debug.

The weekly-review Routine needs its own environment, or its own Routine-level
model setting, with `TRADING_AGENT_MODEL=claude-opus-5`.

## Reference

- [Configure cloud environments](https://code.claude.com/docs/en/cloud-environments)
- [Network access levels](https://code.claude.com/docs/en/cloud-environments#access-levels)
- [Add API credentials](https://code.claude.com/docs/en/cloud-environments#add-api-credentials)
- [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web)
