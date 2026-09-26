# Effort routing: notes for the Friday-evening design session

Prepared 2026-09-25 ~00:45 ET for discussion with recalcitrantmaus on
the evening of Friday 2026-09-25. Nothing here is decided. It is the input
to a decision.

## What is measured

| # | Observation | When |
|---|---|---|
| 1 | `CLAUDE_EFFORT` tracks the **turn**. One session read `high` at 13:39Z and `medium` at 20:07Z. | 2026-09-22 |
| 2 | A runner made with `create_session` comes up at `high`. The tool has no effort parameter, and `high` is the CLI default. | 2026-09-24 rehearsal 1, both runners |
| 3 | Setting `"effortLevel": "xhigh"` in `.claude/settings.json` did not change what the runners read: the Opus runner read `medium`, the Sonnet runner `high`. The setting was reverted in `1a40f2a`. | rehearsal 2 |
| 4 | At the same moment as #3, the Opus runner's **session record** showed `effort_level: xhigh` from the picker, while its shell read `CLAUDE_EFFORT=medium`. | rehearsal 2 |
| 5 | recalcitrantmaus then set both runners to Opus at Extra high in the UI. The midday runner is now **Opus**, not Sonnet (`user_switched_model`). | 2026-09-24 ~00:40 ET |
| 6 | `model_check` prefers `CLAUDE_EFFORT` (source "harness") over `TRADING_AGENT_EFFORT` (source "declared"). | `engine/model_policy.py` `effort_and_source()` |

## What is not known

- **Which number is the served effort.** Is it the session record's
  `effort_level`, or the shell's `CLAUDE_EFFORT`? #4 shows they can disagree,
  and we have no third reading to break the tie.
- **Whether a trigger-fired turn inherits the picker's effort.** Friday answers
  this: every firing reports `CLAUDE_EFFORT`. Compare those readings with the
  session records afterwards.
- **Why a rehearsal turn read `medium`**, below the CLI default.

## Options

**A. Read effort the way we already read the model.** The session record is
the source, the model passes it with `--effort` (the flag exists), and
`model_check` labels the source "session record". This is symmetrical with
how `--model` works today. It does not settle #4. It only chooses which of the
two values to believe.

**B. Stop gating unattended trading tasks on effort.** Record the value on
every firing instead. The trading floors already only warn. This makes that
explicit and removes the noise. Effort stays a hard gate only on blocking
tasks, which are attended by rule (they need a human's `--authorization`), so
a person can confirm the picker directly. This is CLAUDE.md's "earn the floor
down" applied to effort rather than to the model.

**C. Move the schedule to Routines built in the claude.ai UI** (repo attached,
fresh session per firing). HANDOFF already recommends this for Phase 3
connectors and notifications. **Unverified:** whether the UI lets a Routine
pin its effort. Check in the UI before counting on it.

**D. Measure before designing.** A controlled test: one session, the picker
set, then a trigger-fired turn and a typed turn, reading the session record
and `CLAUDE_EFFORT` in each. About 15 minutes, and it answers #4 directly.

## Proposal to discuss

**D first, then B, with A for blocking tasks.**
- Measure what a fired turn actually gets.
- For unattended trading firings: record the effort each turn reads, never
  gate on it, and keep the model-tier check.
- For blocking tasks, which are attended by rule: the human confirms the
  picker, and `model_check` takes `--effort` from the session record,
  labelled as such.
- Look at **C** separately, as part of the Phase 3 move.

Any of these that touches `engine/model_policy.py` needs a test, a
`docs/04-lessons.md` entry, and a rule-promotion clearance with recalcitrantmaus's
authorization.

## Inputs from Friday to bring to the discussion

- `CLAUDE_EFFORT` as reported by each firing (in the relay reports and the
  journal).
- Each runner's session record `effort_level`, read afterwards with
  `get_session`.
- Whether any firing's behaviour looked degraded, which is the real question
  the floor exists for.

---

## Decision, 2026-09-26 (attended, authorized by recalcitrantmaus)

Option D, measure first, was answered by today's own session:

| observation | value |
|---|---|
| session record `effort_level` | xhigh throughout |
| harness `CLAUDE_EFFORT`, three turns | **medium** |
| `flag_settings_seq` during those turns | 14, unchanged |
| a second client (VS Code) attached, set to | medium |
| after closing it and toggling the web picker | seq **923**, `CLAUDE_EFFORT=xhigh` |

**The harness value is the served value. The session record and the picker
can be stale.** That rejects option A, which would read effort from the
session record: it would have cleared the review at medium. The gate that
refused was right, and it stays the source of truth.

Built (engine, E-1 in `docs/04-lessons.md`):
1. The harness value outranks an explicit `--effort`. A contradicting
   `--effort` is refused on a blocking task. Before this, it cleared one.
2. Every below-floor refusal now carries the remedy that actually worked
   (close other clients, toggle the picker, re-send).
3. Option B holds as already built: trading tasks warn and continue, and
   each firing reports the effort it read.

Not built, and why: an effort log file. Each firing already reports its
effort in the committed relay report, and a second copy would only be noise.
