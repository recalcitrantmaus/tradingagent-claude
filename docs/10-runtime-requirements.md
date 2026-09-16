# Runtime requirements for a scheduled session

What a fired session must have before it is allowed to trade, ordered by how
badly it fails without it. Written after the first scheduled firing on
2026-09-16 came up in an empty container and could do nothing at all.

## 1. The repository, attached at session start — NOT clonable on demand

The first firing failed here. The container came up with no repo, so every
step failed at step 1 and the session traded nothing.

**It cannot bootstrap itself out of this.** Two independent reasons:

- the repository is **private**, so an unauthenticated clone fails; and
- `git clone` in an unattended session is **refused by the permission
  classifier**, verified directly — a source-less test session reported
  "repo clone denied by permission classifier" and stopped. There is no human
  present to approve the prompt, and there must not be a way around that.

**A Routine created through the `create_trigger` MCP tool does not carry a git
source.** Its stored config reads `"sources":[], "outcomes":[]` — a
"fresh session on fire" inherits the *environment* (env vars, network policy),
not the repository. The tool exposes no `sources` parameter, so this cannot be
fixed from inside a session that uses it.

Two configurations that do work:

| Approach | Repo | Sessions | Cost |
|---|---|---|---|
| Create the Routine in the **claude.ai Routines UI** with the repo attached | yes | fresh each firing | one-time manual setup |
| `create_session(source_url=…, outcome_branch=…)`, then bind triggers to it with `persistent_session_id` | yes | one shared session | context accumulates across firings |

The second was verified working on 2026-09-16: repo present, git clean, all
six skills loaded natively, `preflight_phase2` green.

## 2. Never hardcode the repository path

The path depends on how the session was created:

| Session origin | Path |
|---|---|
| `web_claude_ai` with a source | `/home/user/tradingagent-claude` |
| `create_session(source_url=…)` | `/root/trading-agent-robinhood-cb9xo7` (branch name) |

The second is named for the **branch**, not the repo. Every prompt written
before this was discovered hardcoded the first path and would have failed even
with the repo present. Locate it instead:

```bash
cd "$(git -C /root/trading-agent-robinhood-cb9xo7 rev-parse --show-toplevel 2>/dev/null \
      || git -C /home/user/tradingagent-claude rev-parse --show-toplevel 2>/dev/null \
      || find / -maxdepth 4 -name CLAUDE.md -path '*trading*' -printf '%h\n' 2>/dev/null | head -1)"
```

## 3. Environment-level, inherited correctly by fired sessions

These come from the environment (`Custom - Trading Agent`) and were never the
problem, but a session must still confirm them rather than assume:

- `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`
- `TRADING_AGENT_MODEL`, `TRADING_AGENT_EFFORT`
- the network allowlist (Alpaca, primary sources, news outlets)
- Python 3 — the code is standard-library only by design, so there is nothing
  to install and nothing to keep patched

## 4. Skills

`.claude/skills/` ships with the repo and loads **natively at session start**
when the repo is attached — confirmed, all six. A repo cloned mid-session
would not get this, which is a further reason the clone-on-demand path is not
merely blocked but wrong.

## 5. MCP connectors — inert now, disqualifying at Phase 3

Routines created in-session store no connectors. Alpaca is plain HTTPS through
`urllib`, so Phase 2 does not care. Robinhood agentic trading is an MCP
server, so Phase 3 does. See `docs/07-deployment.md` section 6.

## The rule this produces

**A session that cannot verify 1 through 3 must not trade.** It has no risk
engine, no ledger, no `CLAUDE.md` — nothing that makes an order safe. The
correct behaviour is to stop and report, never to improvise an order against
the broker API from memory. `python3 -m tools.preflight_phase2` now checks the
repository first, and exits non-zero if the work tree, the branch, the origin
remote or the fetch is missing.
