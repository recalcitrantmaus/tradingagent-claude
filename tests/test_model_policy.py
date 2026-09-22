"""The model gate decides what the agent is allowed to BECOME.

Measured 2026-09-18: a session verified as claude-opus-5 from its own session
record read `claude-sonnet-5` from TRADING_AGENT_MODEL, because that variable
is set at the ENVIRONMENT level and is identical for every session launched
there. The gate was answering a per-session question with an environment-wide
constant, and it was right only by coincidence.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.model_policy import check, model_and_source, POLICY


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

    def test_an_explicit_model_clears_a_blocking_task(self):
        with env(TRADING_AGENT_MODEL="claude-sonnet-5", TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-opus-5")
        self.assertTrue(ok)

    def test_an_explicit_model_that_is_too_weak_still_fails(self):
        with env(TRADING_AGENT_EFFORT="xhigh"):
            ok, msgs = check("weekly-review", model="claude-haiku-4-5-20251001")
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
        with env(CLAUDE_EFFORT="high", TRADING_AGENT_EFFORT="xhigh",
                 CLAUDE_CODE_SESSION_ATTENDED="1"):
            ok, msgs = check("execution", model="claude-opus-5")
        self.assertTrue(any("EFFORT MISMATCH" in m for m in msgs))

    def test_a_blocking_task_refuses_a_declared_only_effort(self):
        with mock.patch.dict(os.environ, {"TRADING_AGENT_EFFORT": "xhigh",
                                          "CLAUDE_CODE_SESSION_ATTENDED": "1"},
                             clear=True):
            ok, msgs = check("weekly-review", model="claude-opus-5")
        self.assertFalse(ok)
        self.assertTrue(any("UNVERIFIED" in m for m in msgs))


class TestOverrideRequiresAHuman(unittest.TestCase):
    """M-22. --model exists so a session that has verified its own model can
    clear a blocking gate. That is a human's act, asserted on a session record
    a human has read. An unattended session reaching for it is overriding on
    its own say-so, which is the thing the gate exists to prevent.

    The close session on 2026-09-21 reached this unprompted and declined the
    flag. These tests make its judgement the rule.
    """

    def test_an_unattended_session_cannot_override_a_blocking_gate(self):
        with env(CLAUDE_EFFORT="xhigh", CLAUDE_CODE_SESSION_ATTENDED="0"):
            ok, msgs = check("weekly-review", model="claude-opus-5")
        self.assertFalse(ok)
        self.assertTrue(any("UNATTENDED" in m for m in msgs))

    def test_a_missing_attended_flag_is_treated_as_unattended(self):
        # Fail closed. A blocked review costs a review; a rule promoted by an
        # under-powered unattended session costs every trade until noticed.
        with mock.patch.dict(os.environ, {"CLAUDE_EFFORT": "xhigh"}, clear=True):
            ok, _ = check("weekly-review", model="claude-opus-5")
        self.assertFalse(ok)

    def test_an_attended_session_may_override(self):
        with env(CLAUDE_EFFORT="xhigh", CLAUDE_CODE_SESSION_ATTENDED="1"):
            ok, msgs = check("weekly-review", model="claude-opus-5")
        self.assertTrue(ok)

    def test_a_NON_blocking_task_is_unaffected_by_attendance(self):
        # Execution must never be gated on a human being present.
        with env(CLAUDE_EFFORT="xhigh", CLAUDE_CODE_SESSION_ATTENDED="0"):
            ok, _ = check("execution", model="claude-sonnet-5")
        self.assertTrue(ok)
