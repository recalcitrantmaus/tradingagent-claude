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
