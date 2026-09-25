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

## 2. Never hardcode the repository path — it is not stable

Three different paths have been observed for the same repository:

| Observation | Path |
|---|---|
| This interactive session (`web_claude_ai` with a source) | `/home/user/tradingagent-claude` |
| `create_session(source_url=…)`, first turn | `/root/trading-agent-robinhood-cb9xo7` |
| **The same session** after its container was re-provisioned | `/home/user/trading-agent` |

The third is the one that matters. The path changed *within a single session*,
across a container re-provision, with no change to the session config. So it is
not enough to discover the path once at session start and reuse it — a
long-lived runner woken by a trigger hours later may find itself somewhere else.

Every session must locate the repository at the start of **every** turn, and
must never carry a path forward from a previous turn:

```bash
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || REPO="$(find / -maxdepth 5 -name CLAUDE.md -path '*trading*' \
             -printf '%h\n' 2>/dev/null | head -1)"
[ -n "$REPO" ] || { echo "no repository — DO NOT TRADE"; exit 1; }
cd "$REPO"
```

The session normally starts inside the work tree, so `git rev-parse` alone
usually answers it. The fallback exists because the failure mode is silent: a
`cd` to a stale path lands in a directory that does not exist, and every
subsequent command fails in a way that looks like a broken tool rather than a
missing repo.

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

## 6. Effort — `create_session` cannot set it, and neither can the repository

Measured 2026-09-24 ET in the rehearsal for Friday 2026-09-25: two runner
sessions created with `create_session` (one Opus, one Sonnet) both came up
at `CLAUDE_EFFORT=high`, while `TRADING_AGENT_EFFORT` declared `xhigh`. The
MCP tool has no effort parameter, and the CLI's default is `high`, which is
below the `xhigh` floor on every trading task except news-intel. The session
that created them was at `xhigh` from its own picker, and they do not inherit
it.

Tried and reverted the same night: `"effortLevel": "xhigh"` in
`.claude/settings.json`. After pulling it, the Opus runner read
`CLAUDE_EFFORT=medium` and the Sonnet runner read `high`. The Opus runner's
session record showed `effort_level: xhigh` from the picker at the same time.
So neither the repo setting nor the picker is confirmed to reach
`CLAUDE_EFFORT`, and which of the two values is the served effort is
unresolved (T-15). The trading tasks are non-blocking, so a firing below the
floor warns, continues and records it. Nothing blocking is scheduled
unattended.

## 7. Permissions — how an unattended command actually gets approved

Found 2026-09-25, when the open was refused ("Modify Shared Resources").
Full analysis: `state/reviews/2026-09-25-permissions-rca.md`.

Runners run in **auto mode**, where a Bash command is approved in one of two
ways:

1. **An allow rule in `.claude/settings.json` matches the whole command.**
   Auto mode strips rules that would allow arbitrary code
   (`Bash(python3 -c:*)`, `Bash(python3:*)`), but keeps
   `Bash(python3 -m tools.X:*)`.
2. **Otherwise the auto-mode classifier judges it** against the intent in the
   session's transcript. That is a judgment call made fresh each time, and
   today it went the other way.

Until 2026-09-25, every prompt sent compound commands
(`REPO="$(…)"; cd "$REPO"; python3 -m …`) and `python3 -c` one-liners.
Neither matches a rule, so **the classifier decided every firing of the
week.** Rules that govern this:

- **One command per Bash call, written exactly as the allowlist spells it.**
  No `cd`, no `REPO=`, no `&&`, `;` or `|`, no `2>&1`. The session already
  starts in the repository, and preflight verifies it. This replaces §2's
  `cd "$REPO"` recipe. Each turn still checks where it is, with a single
  `git rev-parse --show-toplevel`. If that is not the repository, the turn
  stops and reports; it does not `cd` its way out.
- **No `python3 -c`.** Broker state comes from `python3 -m tools.broker_check`.
- **Never rehearse inside a session that will trade.** A "read-only, do not
  trade" instruction stays in that session's transcript and is the likeliest
  reason the classifier refused the open. Rehearse in a throwaway session,
  and scope any restriction to "this turn only".
- **`autoMode` settings cannot be set from the repository.** The CLI ignores
  `autoMode` in project and local settings ("only user/flag/managed settings
  may set classifier rules"; measured in the 2.1.282 binary). Standing
  classifier context has to come from the environment or user settings,
  outside this repo.

## The rule this produces

**A session that cannot verify 1 through 3 must not trade.** It has no risk
engine, no ledger, no `CLAUDE.md` — nothing that makes an order safe. The
correct behaviour is to stop and report, never to improvise an order against
the broker API from memory. `python3 -m tools.preflight_phase2` now checks the
repository first, and exits non-zero if the work tree, the branch, the origin
remote or the fetch is missing.
