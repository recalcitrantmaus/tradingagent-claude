import contextlib
import io
import json
import unittest
from types import SimpleNamespace as NS

from tools import ma_poc


class ConfigTest(unittest.TestCase):
    def test_model_and_effort_are_pinned_on_the_agent(self):
        cfg = ma_poc.agent_config()
        self.assertEqual(cfg["model"], {"id": "claude-opus-5-5", "effort": "xhigh"})

    def test_no_trading_tools_are_granted(self):
        self.assertNotIn("tools", ma_poc.agent_config())
        self.assertNotIn("mcp_servers", ma_poc.agent_config())


class VerifyTest(unittest.TestCase):
    def test_effort_echoed_as_a_string(self):
        agent = {"model": {"id": "claude-opus-5-5", "effort": "xhigh"}}
        self.assertEqual(ma_poc.verify(agent), [])

    def test_effort_echoed_in_object_form(self):
        agent = NS(model=NS(id="claude-opus-5-5", effort=NS(type="xhigh")))
        self.assertEqual(ma_poc.verify(agent), [])

    def test_missing_effort_fails_and_says_the_default_applies(self):
        problems = ma_poc.verify({"model": {"id": "claude-opus-5-5"}})
        self.assertEqual(len(problems), 1)
        self.assertIn("model default", problems[0])

    def test_bare_string_model_carries_no_effort(self):
        self.assertTrue(ma_poc.verify({"model": "claude-opus-5-5"}))

    def test_lower_effort_or_other_model_fails(self):
        self.assertTrue(ma_poc.verify(
            {"model": {"id": "claude-opus-5-5", "effort": "medium"}}))
        self.assertTrue(ma_poc.verify(
            {"model": {"id": "claude-sonnet-5", "effort": "xhigh"}}))


class DryRunTest(unittest.TestCase):
    def test_default_sends_nothing(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ma_poc.main([])
        self.assertEqual(rc, 0)
        self.assertIn("dry run: nothing sent", buf.getvalue())
        json.loads(buf.getvalue().split("\n\ndry run")[0])


if __name__ == "__main__":
    unittest.main()
