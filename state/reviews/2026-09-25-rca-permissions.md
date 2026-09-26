# Root cause: the 2026-09-25 open was refused by the permission layer (F-1)

Written by the arming session, 2026-09-25 ~11:10 ET, at recalcitrantmaus's request. It is
input to the Friday-evening design session, alongside
`2026-09-25-design-effort.md`.

## What happened

At 09:46 ET the Opus runner ran `preflight_phase2`, which passed. Claude
Code's **auto-mode classifier** then refused `tools.trading_day open`, and
also a call to `tools.netcheck` and `tools.status`, with the reason "Modify
Shared Resources". Nothing in `engine/` was involved. The runner stood down,
as its prompt required.

## The two layers that decide whether a Bash command runs

1. **Allow rules** (`.claude/settings.json`). In auto mode, rules that would
   let an interpreter run anything are removed
   (`stripDangerousPermissionsForAutoMode`). Measured in the CLI source:
   `Bash(python3 -m tools.X:*)` survives, because it names a dotted module, so
   our rules are still live. **A rule only matches a whole command, though.**
   The prompts send compound commands (`REPO="$(git rev-parse …)"; cd
   "$REPO"; …`, or two tools chained). A compound command is not covered by
   any single rule, so it falls through to layer 2.
2. **The classifier.** A model judges the action against the user's intent as
   expressed in the session's transcript.

## Root cause

**This week the allowlist was not what let the runners trade. The classifier
was.** Every firing's compound commands went to it, and until today it judged
"reconcile and submit a paper order" to be what the user wanted. That is a
judgment call made fresh each time. It is not a grant.

**What changed today is the transcript. I caused it.** Before the open, this
runner's session had received two rehearsal prompts from me:
- rehearsal 1: "Do NOT trade, submit, cancel or modify any order. Do NOT edit
  or commit any file. Read-only."
- rehearsal 2: "Still read-only: no trades, no edits, no commits."

The 09:45 firing then asked it to reconcile and trade. Trigger-delivered
prompts are marked `isSynthetic`. The classifier saw earlier explicit
instructions forbidding modification, followed by a synthetic turn asking for
it, and refused. It refused even `tools.status`, which is read-only, which
points to the session's context rather than the individual command.
Wednesday's runner never had a "read-only" instruction in its history.

**Confidence:** high that the classifier made the decision, and that the
compound commands were what routed them to it. Moderate on the transcript
explanation. It is the only difference I can identify, but I cannot read the
classifier's reasoning or the runner's transcript. A minor unverified
difference: the runner's CLI is 2.1.282, and Wednesday's was 2.1.280.

## Why the rehearsals did not catch it

They were read-only by design, so they never exercised a write. Worse, the
read-only instruction is what contaminated the session that had to trade.

## Fix options for the design session

1. **Never rehearse inside the session that will trade.** Rehearse in a
   throwaway session, or scope the instruction explicitly ("for this turn
   only"). Cheap, and it removes today's trigger.
2. **Make each command match an allow rule exactly.** One tool per Bash call.
   No `REPO=$(…)` or `cd` prefix: the session starts in the repo, and
   preflight already verifies that. Then the classifier is not consulted for
   the trading spine at all. This removes the underlying fragility. Needs a
   prompt change and a quick test in a fresh session.
3. **Give the classifier standing context.** `autoMode.environment` and
   `autoMode.allow` entries exist in the settings schema. For example, "this
   repository is a paper-trading agent; scheduled Routine prompts are the
   owner's authorized instructions to run tools.trading_day and
   tools.paper_session". **Unverified:** whether project-level settings are
   honored for these, or only user/managed settings.
4. **Explicit rules for the remaining gaps** (git push by name, `python3 -c`
   broker checks). Put the `-c` one-liners into a `tools.` module, so a module
   rule covers them instead of an interpreter wildcard.

Recommended: 1 and 2 now, since they are cheap and testable today; 3 after
verifying where it is honored; 4 as cleanup. Rehearse with a real
state-writing command in a fresh session before arming the next day.
