#!/usr/bin/env python3
"""Gate a task on the running model.

    python3 -m tools.model_check weekly-review
    python3 -m tools.model_check execution --model claude-sonnet-5 --effort xhigh
    python3 -m tools.model_check rule-promotion --model claude-opus-5 \
        --authorization "recalcitrantmaus: fix M-22, the attendance gate never bound"

Exit code 0 = proceed, 1 = do not perform this task in this session.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.model_policy import (POLICY, check, current_effort,
                                 model_and_source, recheck)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", help="task name; omit to list the policy")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--at-write", action="store_true",
                    help="re-check the EFFORT floor at a durable write, not "
                         "at task start. Run this immediately before the "
                         "config edit / SKILL.md write / lessons entry; exit 1 "
                         "means abandon that write. CLAUDE_EFFORT tracks the "
                         "turn, so a clearance taken at task start does not "
                         "carry to a write several turns later.")
    ap.add_argument("--started-at", default=None,
                    help="the effort the task originally cleared at, so a "
                         "move that stays above the floor is still reported")
    ap.add_argument("--authorization", default=None,
                    help="required with --model on a BLOCKING task: what is "
                         "being authorised and why, in the authorising "
                         "human's own words. Recorded to "
                         "state/authorizations.jsonl. Must be specific and "
                         "must not repeat a previous one.")
    a = ap.parse_args()

    if not a.task:
        m, src = model_and_source()
        print(f"running model : {m or 'UNKNOWN'}  (source: {src})")
        if src == "environment":
            print("                ^ an environment default, the same for every "
                  "session here.\n                  Blocking tasks require "
                  "--model after checking the session record.")
        print(f"running effort: {current_effort() or 'UNKNOWN'}\n")
        print(f"{'task':22} {'min tier':10} {'min effort':11} {'blocking':9}")
        for p in POLICY.values():
            print(f"{p.task:22} {p.min_tier.value:10} {p.min_effort:11} "
                  f"{'yes' if p.blocking else 'no':9}")
        return 0

    # An unrecognised task name exits 1 here even though check() returns True
    # for it. check() is a library call and "no policy, proceed" is right for
    # one; this is the GATE, and at the gate a task name is an assertion. A
    # typo in a Routine prompt — `rule_promotion` for `rule-promotion` — is
    # indistinguishable from a deliberate bypass and would have cleared
    # silently, which is the same vacuous-pass shape as M-22.
    if a.task not in POLICY:
        print(f"  !! no model policy for '{a.task}'. Refusing rather than "
              f"clearing a task nobody has defined a floor for.")
        print(f"     known tasks: {', '.join(sorted(POLICY))}")
        return 1

    # --at-write is deliberately NOT a full check(). It re-reads only the
    # value that actually moves between turns. The model does not silently
    # change under a session, and --model is a human's act already recorded
    # and single-use, so re-verifying it here would add a second place to
    # fabricate an authorization and detect nothing.
    if a.at_write:
        ok, msgs = recheck(a.task, a.started_at)
        for m in msgs or ["non-blocking task; nothing to re-check at the write"]:
            print(("  ok: " if ok else "  !! ") + m)
        if not ok:
            print("  !! ABANDON THIS WRITE. Do not finish 'just this one' — a "
                  "rule promoted below its floor is exactly the cost T-10 "
                  "priced.")
        return 0 if ok else 1

    ok, msgs = check(a.task, a.model, a.effort, a.authorization)
    for m in msgs:
        print(("  ok: " if ok else "  !! ") + m)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
