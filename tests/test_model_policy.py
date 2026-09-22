"""The model gate decides what the agent is allowed to BECOME.

Measured 2026-09-18: a session verified as claude-opus-5 from its own session
record read `claude-sonnet-5` from TRADING_AGENT_MODEL, because that variable
is set at the ENVIRONMENT level and is identical for every session launched
there. The gate was answering a per-session question with an environment-wide
constant, and it was right only by coincidence.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.model_policy import check, model_and_source, POLICY

# Every blocking task now needs an authorization, and the gate refuses a
# REUSED one — so tests that merely need a blocking task to clear must mint a
# fresh string each time and write to a throwaway log, never the repo's.
_LOG = Path(tempfile.mkdtemp()) / "authorizations.jsonl"
_N = [0]


def _auth() -> str:
    _N[0] += 1
    return f"recalcitrantmaus: test authorization {_N[0]}, specific enough to be real"


def env(**kw):
    return mock.patch.dict(os.environ, kw, clear=False)


class TestProvenance(unittest.TestCase):
    def test_an_environment_value_is_labelled_as_one(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5"):
            self.assertEqual(model_and_source(), ("claude-sonnet-5", "environment"))

    def test_absence_is_unknown_not_a_guess(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(model_and_source(), (None, "unknown"))


class TestBlockingTasksRefuseAnUnverifiedModel(unittest.TestCase):
    """The asymmetry is deliberate. Today the environment says sonnet and the
    gate fails closed, which is safe. That is luck, not design: setting
    TRADING_AGENT_MODEL to an opus id would make EVERY session in the
    environment clear, whatever it actually runs. So a blocking task does not
    accept an environment default at all, in either direction.
    """

    def test_blocking_refuses_even_when_the_env_value_would_pass(self):
        with env(TRADING_AGENT_MODEL="claude-opus-5", TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("weekly-review")
        self.assertFalse(ok)
        self.assertTrue(any("UNVERIFIED" in m for m in msgs))

    def test_blocking_refuses_when_the_env_value_would_fail(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5", TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("weekly-review")
        self.assertFalse(ok)

    def test_the_refusal_says_how_to_fix_it(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5"):
            _, msgs = check("weekly-review")
        blob = " ".join(msgs)
        self.assertIn("--model", blob)
        self.assertIn("session record", blob)

    # These two are about the MODEL half of the gate, so the effort and
    # attendance halves are pinned rather than inherited. `env()` patches with
    # clear=False, so an unpinned value falls through to the ambient
    # environment — and on 2026-09-22 that made this class a test OF the
    # environment: it was green overnight on CLAUDE_EFFORT=xhigh and red at
    # 09:35 on CLAUDE_EFFORT=high, with no code change in between. A test that
    # asserts something about the gate must not be decided by the machine it
    # runs on.
    def test_an_explicit_model_clears_a_blocking_task(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5", TRADING_AGENT_EFFORT="xhigh",
                 CLAUDE_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-opus-5",
                             authorization=_auth(), auth_log=_LOG)
        self.assertTrue(ok)

    def test_an_explicit_model_that_is_too_weak_still_fails(self):
        with env(TRADING_AGENT_EFFORT="xhigh", CLAUDE_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-haiku-4-5-20251001",
                             authorization=_auth(), auth_log=_LOG)
        self.assertFalse(ok)
        self.assertTrue(any("requires" in m for m in msgs))


class TestNonBlockingTasksProceedButSayWhereTheValueCameFrom(unittest.TestCase):
    def test_execution_proceeds_on_an_environment_value(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5", TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("execution")
        self.assertTrue(ok)
        self.assertTrue(any("environment default" in m for m in msgs))

    def test_a_downgrade_on_a_non_blocking_task_still_proceeds(self):
        with env(TRADING_AGENT_EFFORT="low"):
            ok, msgs = check("execution", model="claude-haiku-4-5-20251001")
        self.assertTrue(ok)
        self.assertTrue(any("non-blocking" in m for m in msgs))


class TestPolicyShape(unittest.TestCase):
    def test_the_rule_changing_tasks_are_the_blocking_ones(self):
        # If this fails someone has made a rule-promotion task non-blocking,
        # which is the single change that would quietly undo this whole gate.
        for t in ("weekly-review", "rule-promotion", "unlock-authorization"):
            self.assertTrue(POLICY[t].blocking, f"{t} must be blocking")
        for t in ("execution", "news-intel", "trade-journal"):
            self.assertFalse(POLICY[t].blocking, f"{t} must not be blocking")


class TestEffortIsMeasuredNotDeclared(unittest.TestCase):
    """M-17. Unlike the model, the harness DOES export the effort level
    (CLAUDE_EFFORT). The policy read TRADING_AGENT_EFFORT — a declaration set
    once per environment — and on 2026-09-21 they disagreed: declared xhigh,
    actually running high. The gate cleared an effort the session was not
    running at, permissively, on a value sitting in the environment all along.
    """

    def test_the_harness_value_wins_over_the_declaration(self):
        with env(CLAUDE_EFFORT="high", TRADING_AGENT_EFFORT="xhigh"):
            from engine.model_policy import effort_and_source
            self.assertEqual(effort_and_source(), ("high", "harness"))

    def test_the_declaration_is_a_fallback_and_is_labelled(self):
        with mock.patch.dict(os.environ, {"TRADING_AGENT_EFFORT": "xhigh"},
                             clear=True):
            from engine.model_policy import effort_and_source
            self.assertEqual(effort_and_source(), ("xhigh", "declared"))

    def test_a_mismatch_is_reported_loudly(self):
        with env(CLAUDE_EFFORT="high", TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("execution", model="claude-opus-5")
        self.assertTrue(any("EFFORT MISMATCH" in m for m in msgs))

    def test_a_blocking_task_refuses_a_declared_only_effort(self):
        with mock.patch.dict(os.environ, {"TRADING_AGENT_EFFORT": "xhigh"},
                             clear=True):
            ok, msgs = check("weekly-review", model="claude-opus-5",
                             authorization=_auth(), auth_log=_LOG)
        self.assertFalse(ok)
        self.assertTrue(any("UNVERIFIED" in m for m in msgs))




class TestOverrideMustBeAuthorised(unittest.TestCase):
    """M-22, second attempt — the first one never bound.

    `is_attended()` read CLAUDE_CODE_SESSION_ATTENDED, which is set
    environment-wide, so it was "1" in every session and the gate never once
    refused. On 2026-09-22 an unattended scheduled session cleared
    `rule-promotion` through it, measured end to end.

    The fix proposed at the time — require that variable to equal the session
    id, so an environment-wide value satisfies at most one session — is ALSO
    wrong, and the session that proposed it is the counterexample: a scheduled
    relay fired into it at 14:20Z (unattended), a human typed into it at
    15:45Z (attended), same session id and same environment throughout.
    Attendance is a property of the TURN, and environment variables are
    snapshotted at session start, so no variable of any scope can track it.

    The override is therefore no longer DETECTED. It is declared and recorded.
    That is attributable, not enforceable, and these tests pin only the two
    properties that are genuinely enforced: an authorization must say
    something, and it must not be reusable — because the realistic threat is
    not an adversarial agent, it is a canned string in a Routine prompt that
    would otherwise clear this gate on every firing, forever.
    """

    def setUp(self):
        self.log = Path(tempfile.mkdtemp()) / "authorizations.jsonl"

    def test_a_blocking_task_refuses_without_an_authorization(self):
        with env(CLAUDE_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-opus-5",
                             auth_log=self.log)
        self.assertFalse(ok)
        self.assertTrue(any("authorization" in m for m in msgs))

    def test_a_trivial_authorization_is_refused(self):
        for junk in ("ok", "yes", "approved", "1", "   ", "go ahead", ""):
            with env(CLAUDE_EFFORT="xhigh"):
                ok, _ = check("weekly-review", model="claude-opus-5",
                              authorization=junk, auth_log=self.log)
            self.assertFalse(ok, f"{junk!r} should not clear a blocking gate")

    def test_a_reused_authorization_is_refused(self):
        text = "recalcitrantmaus: promote the 2% cap change, evidence in docs/04"
        with env(CLAUDE_EFFORT="xhigh"):
            ok, _ = check("weekly-review", model="claude-opus-5",
                          authorization=text, auth_log=self.log)
            self.assertTrue(ok)
            ok, msgs = check("weekly-review", model="claude-opus-5",
                             authorization=text, auth_log=self.log)
        self.assertFalse(ok)
        self.assertTrue(any("used before" in m for m in msgs))

    def test_reuse_is_detected_through_whitespace_and_case(self):
        with env(CLAUDE_EFFORT="xhigh"):
            check("weekly-review", model="claude-opus-5",
                  authorization="recalcitrantmaus: raise the position cap to 30%",
                  auth_log=self.log)
            ok, _ = check("weekly-review", model="claude-opus-5",
                          authorization="  recalcitrantmaus:   RAISE the Position cap to 30%  ",
                          auth_log=self.log)
        self.assertFalse(ok)

    def test_a_specific_authorization_clears_and_is_recorded(self):
        with env(CLAUDE_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-opus-5",
                             authorization="recalcitrantmaus: fix M-22, the gate never bound",
                             auth_log=self.log)
        self.assertTrue(ok)
        rows = [json.loads(x) for x in self.log.read_text().splitlines() if x.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task"], "weekly-review")
        self.assertEqual(rows[0]["model"], "claude-opus-5")
        self.assertIn("M-22", rows[0]["authorization"])
        self.assertTrue(rows[0]["ts"])

    def test_a_refused_run_does_not_burn_the_authorization(self):
        # Refused on tier, so the nonce must survive to be used properly.
        with env(CLAUDE_EFFORT="xhigh"):
            ok, _ = check("weekly-review", model="claude-haiku-4-5-20251001",
                          authorization="recalcitrantmaus: deliberately try the cheap model",
                          auth_log=self.log)
            self.assertFalse(ok)
            ok, _ = check("weekly-review", model="claude-opus-5",
                          authorization="recalcitrantmaus: deliberately try the cheap model",
                          auth_log=self.log)
        self.assertTrue(ok)

    def test_a_NON_blocking_task_needs_no_authorization(self):
        # Execution must never wait on a human. This is what keeps the fix
        # from ever reaching the trading path.
        with env(CLAUDE_EFFORT="xhigh"):
            ok, _ = check("execution", model="claude-sonnet-5", auth_log=self.log)
        self.assertTrue(ok)

    def test_the_old_environment_flag_no_longer_clears_anything(self):
        # The regression that matters. If CLAUDE_CODE_SESSION_ATTENDED is ever
        # honoured again, this goes red.
        with env(CLAUDE_EFFORT="xhigh", CLAUDE_CODE_SESSION_ATTENDED="1"):
            ok, _ = check("weekly-review", model="claude-opus-5",
                          auth_log=self.log)
        self.assertFalse(ok)

    def test_a_corrupt_log_row_does_not_break_the_gate(self):
        self.log.write_text("not json at all\n")
        with env(CLAUDE_EFFORT="xhigh"):
            ok, _ = check("weekly-review", model="claude-opus-5",
                          authorization="recalcitrantmaus: a real and specific reason here",
                          auth_log=self.log)
        self.assertTrue(ok)
