# Friday 2026-09-25 — findings queue

Shared by all of today's firings. Continue the sequence; never renumber.

## F-1 — The open firing was stopped at step 0 by the session's permission check, not by the engine

- **When:** 2026-09-25 ~13:46Z (09:46 ET), Opus runner `session_01Xn54wA68nkt7KHDaoj53RL`, OPEN firing.
- **What:** `python3 -m tools.preflight_phase2` passed (exit 0, 7/7 ok). The next command,
  `python3 -m tools.trading_day open`, was refused by Claude Code's auto-mode permission
  check with the reason "Modify Shared Resources" and was never executed. A separate call running
  `python3 -m tools.netcheck` and `python3 -m tools.status` was refused the same way.
  The two `model_check` calls ran.
- **Effect:** the open spine did not run, so step 0 failed and the firing did not trade, as its
  prompt requires. No brief, plan, screen or order. The runner did not retry the refused commands
  or route around them. The refusal applies to the outcome, not only to those exact commands.
- **Why it matters:** this is a permission layer outside `engine/`. It sits between the Routine and
  the broker, and it treats an unattended firing's order path (reconcile, mark, submit) as a shared-resource
  modification that no one present has approved. The rehearsals did not catch it because
  they ran read-only commands only.
- **Needs (recalcitrantmaus, attended):** decide whether unattended runners may run the trading spine. If yes,
  add explicit Bash permission rules to the runner's settings for the trading commands
  (`tools.trading_day`, `tools.paper_session`, `tools.netcheck`, `tools.status`, `tools.screen`),
  and rehearse one command that actually writes before arming the next day. Until that happens,
  every unattended trading firing should expect the same stop.
