# Effort that holds unattended: design, 2026-09-29

Input to a decision with recalcitrantmaus. Supersedes the "not built" parts of
`2026-09-25-design-effort.md`. Nothing here changes `engine/`.

## recalcitrantmaus's direction (2026-09-29)

- **Long term:** store model and effort *with the agent itself*, where they
  can be referenced. Fall back to setting them in the integration (per
  request) if that does not work.
- **Short term:** "as is" (warn and continue) is not acceptable, because it
  happens in sessions nobody attends and nobody ever will.

## Why every Opus 5.5 turn read "medium" (G-5)

Claude Code's own documentation, fetched 2026-09-29:

- Opus 5.5 defaults to `medium`, one level below every other model's `high`
  (https://code.claude.com/docs/en/model-config, "Default effort per model").
- A session resolves effort as (1) an explicit choice
  (`CLAUDE_CODE_EFFORT_LEVEL`, `--effort`, `/effort`), then (2) settings, then
  (3) the model default (same page, "Precedence").
- Levels are saved **per model** under `modelSettings`, and a top-level
  `effortLevel` in *user* settings is ignored by Opus 5.5
  (https://code.claude.com/docs/en/settings-reference).

So a runner turn with no explicit pick and no per-model setting falls to
`medium`. That explains every reading in G-1 and G-4 without invoking a
restart or a stale picker. The picker toggle "worked" because it is an
explicit choice, and an explicit choice lasts only for that session.

## Does the open still need judgment, now that 2R stays?

**Yes.** D-24 decided how a trade *exits*. The judgment at the open is about
whether a trade should *exist*, and none of it moved:

| Judgment at the open | Where it lives | Mechanical? |
|---|---|---|
| Posture (NEUTRAL / RISK_OFF / NO_TRADE) from news, regime, calendar | premarket-brief | No. Code enforces the posture; the model chooses it |
| Whether a screened breakout "deserves to exist": catalyst, invalidation, counter-case, a news veto | trade-plan | No |
| Whether the feed itself is wrong (the RKLB 20-day high, ATR in 59 of 59 names) | both | Partly. `cross_check()` covers prices; levels and ATR are next |
| Size, stop, target, expected R, portfolio risk | engine | Yes |

And that judgment is exactly what Phase 2 exists to measure: "whether
model-generated theses have positive expectancy" (HANDOFF). Designing effort
out of the open would remove the thing under test. So:

- **Make effort matter less for *correctness*:** keep turning data defects
  into code (levels and ATR cross-checks). That work continues.
- **Pin effort for *judgment*:** the open and the close keep their Opus
  Extra-high floor, and the floor has to be enforceable, not advisory.

## Short term: inside Claude Code (now)

1. **Done, testing:** `.claude/settings.json` sets `modelSettings` to `xhigh`
   for claude-opus-5-5, claude-opus-5 and claude-sonnet-5 (commit `e6d6477`).
   A fresh read-only session (`session_01JQdihEq4RsnTtR6YK7QJjo`) measures a
   typed turn and a trigger-fired turn.
2. **If it does not bind:** recalcitrantmaus adds `CLAUDE_CODE_EFFORT_LEVEL=xhigh` to the
   environment's variables. It is precedence 1, applies to every session in
   the environment, and a new session picks it up.
3. **Proposal, needs authorization (engine):** once effort is pinned, a
   below-floor reading is an anomaly rather than the normal state, so treat it
   as one. On premarket-brief and trade-plan, below the floor means **no new
   entries that day**, and management and the close still run. Today it warns
   and continues. This change touches `engine/model_policy.py` and
   `tools/paper_session.py`, and so needs a test, a lessons entry and recalcitrantmaus's
   authorization. Do it only after (1) or (2) is proven, or it would stand down
   every day.

## Long term: a Managed Agent, with model and effort on the agent

The agent object stores `model` as `{"id": ..., "effort": ...}`. It is
persisted and versioned, and the create and retrieve responses echo it back
(Claude API reference, Managed Agents, "Effort on the agent model"). That is
what "stored with the agent and referenced" means in practice.

| Today (Claude Code routines) | Managed Agents |
|---|---|
| Runner session plus one-shot triggers, re-armed daily by hand | A **scheduled deployment** per firing, cron in `America/New_York`, and a run record per firing |
| Effort from the picker, settings or the model default | `model.effort` on the agent, versioned |
| `model_check` reads `CLAUDE_EFFORT` from the turn | `model_check` reads the **stored agent** by id, and the session cannot certify itself |
| Relay by `create_trigger` into the arming session | `deployment_run.*` webhooks and run records (failed runs are recorded too) |
| Keys in environment variables | Vault credentials, substituted at egress |
| Robinhood MCP needs a connector-bearing Routine | `mcp_servers` on the agent plus a vault |
| No spend cap | `budget` per session, copied from the deployment |

**Known caveats:**

- A per-session `model` override replaces the agent's model object, so an
  override without `effort` runs at the model's default. Never override
  `model` per session, and test for it.
- Scheduled runs are jittered by up to 15% of the interval, capped at 9
  minutes. The 09:45 open may start as late as 09:54.
- Missed runs are not backfilled after a pause.

**Unknowns the POC does not settle:**

1. Whether the *served* effort inside a session can be observed at all.
   There is no known `CLAUDE_EFFORT` equivalent, so the stored pin becomes the
   thing we trust and verify.
2. How state gets back into git. A `github_repository` resource mounts the
   repo, but pushing from the session is unverified.
3. Cost per trading day, measured rather than estimated.

**Fallback (recalcitrantmaus's "set it in the integration"):** a session-level `model`
override that carries `effort`, or the Messages API's
`output_config.effort` per request if we drive the loop ourselves.

## POC: `tools/ma_poc.py` (tests: `tests/test_ma_poc.py`)

- `python3 -m tools.ma_poc` prints the agent config. It is a dry run and sends
  nothing.
- `--create` creates the agent pinned at `claude-opus-5-5` / `xhigh`, stores
  its id in `state/agents/poc.json`, **re-reads it by id** and exits 1 if the
  stored model or effort differ from what was set.
- `--session` also runs one read-only session under a $1.00 platform-enforced
  budget, prints usage, and archives it.

The agent gets no tools, no MCP server and no credentials, so it can do
nothing but answer.

**Blocked on:** an Anthropic API key. This environment has no
`ANTHROPIC_API_KEY`, and variables are read at session start, so the POC runs
from a **new** session once the key is added to the environment. The
container can reach `api.anthropic.com` (HTTP 401 unauthenticated,
2026-09-29).

**Pass criteria:** the stored pin reads back `claude-opus-5-5` / `xhigh`, and
the capped session completes.
