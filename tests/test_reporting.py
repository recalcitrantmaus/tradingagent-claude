"""The reporting tools — what the operator and the next session are told.

These modules place no orders, so nothing here protects a dollar directly.
They protect something slower and harder to recover: the picture of the
account. A status screen that prints NORMAL over a halt, a preflight that
reports green tests while the suite is red, a netcheck that calls a bot-wall
"reachable" — each one licenses a session to trade on a false premise, and the
risk engine cannot help, because the engine is being told the truth about an
account that is not the real one.

Two of these tests exist because the thing they check was wrong when it was
written: `preflight` ran the suite without `-t .` (the invocation that put a
phantom fill in the real ledger on 2026-09-24), and `netcheck` used to call a
403 bot-wall healthy.
"""
import datetime as dt
import io
import json
import re
import subprocess
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]

from adapters import fred
from adapters.base import AdapterError
from engine.sim import SimResult
from sim import capital_sweep, run_suite
from tools import design_doc, model_check, netcheck, smoke_submit, state, status


def ledger(**over):
    d = json.loads(json.dumps(state.EMPTY))
    d.update(over)
    return d


def run_main(fn, argv=None):
    """Call a module main() with a captured stdout and a controlled argv."""
    buf = io.StringIO()
    with mock.patch.object(sys, "argv", argv or ["x"]), redirect_stdout(buf):
        rc = fn()
    return rc, buf.getvalue()


# ======================================================================
# status — the screen read before every market opinion
# ======================================================================
class StatusTests(unittest.TestCase):

    def test_a_normal_account_exits_zero(self):
        with mock.patch.object(state, "load", return_value=ledger()):
            rc, out = run_main(status.main)
        self.assertEqual(rc, 0)
        self.assertIn("NORMAL", out)

    def test_a_halt_exits_non_zero_so_a_caller_cannot_miss_it(self):
        """The printed line is for a human; the exit code is for a script.
        A halt that only prints is a halt a Routine will run straight past."""
        for st in ("HALTED_DAY", "HALTED_WEEK", "LOCKED"):
            with mock.patch.object(state, "load",
                                   return_value=ledger(risk_state=st)):
                rc, out = run_main(status.main)
            self.assertEqual(rc, 1, st)
            self.assertIn(st, out)

    def test_LOCKED_says_a_human_is_required(self):
        with mock.patch.object(state, "load",
                               return_value=ledger(risk_state="LOCKED")):
            _, out = run_main(status.main)
        self.assertIn("human", out.lower())

    def test_a_position_without_a_stop_is_called_out_by_name(self):
        """No stop, no trade is the constitution's rule; a position that has
        lost its stop is the state it exists to prevent, so it cannot be
        reported as just another row."""
        d = ledger(positions={"DT": {"qty": 5, "avg_price": 58.47, "stop": None}})
        with mock.patch.object(state, "load", return_value=d):
            _, out = run_main(status.main)
        self.assertIn("MISSING", out)
        self.assertIn("DT", out)
        self.assertIn("no stop", out.lower())

    def test_a_never_reconciled_ledger_says_do_not_trade(self):
        with mock.patch.object(state, "load",
                               return_value=ledger(last_reconciled=None)):
            _, out = run_main(status.main)
        self.assertIn("NEVER", out)

    def test_equity_comes_from_the_curve_not_from_cash(self):
        """With an open position, cash and equity differ. Reading cash would
        under-report equity by the whole position — and every percentage on
        the screen is computed against it."""
        d = ledger(cash=100.0, equity_curve=[["2026-09-24", 412.5]])
        with mock.patch.object(state, "load", return_value=d):
            _, out = run_main(status.main)
        self.assertIn("412.50", out)

    def test_the_drawdown_peak_includes_todays_equity(self):
        """A new high must not read as a drawdown against a stale peak."""
        d = ledger(peak_equity=300.0, equity_curve=[["2026-09-24", 500.0]])
        with mock.patch.object(state, "load", return_value=d):
            _, out = run_main(status.main)
        self.assertIn("$500.00 / 0.00%", out)


# ======================================================================
# model_check — the routing gate's command-line face
# ======================================================================
class ModelCheckTests(unittest.TestCase):

    def test_no_task_lists_the_policy_and_exits_zero(self):
        rc, out = run_main(model_check.main, ["model_check"])
        self.assertEqual(rc, 0)
        self.assertIn("weekly-review", out)
        self.assertIn("blocking", out)

    def test_a_met_floor_exits_zero(self):
        rc, _ = run_main(model_check.main,
                         ["model_check", "execution", "--model",
                          "claude-opus-5", "--effort", "xhigh"])
        self.assertEqual(rc, 0)

    def test_a_blocking_task_below_its_floor_exits_one(self):
        """Exit 1 is the whole interface. A blocking task that printed a
        warning and exited 0 would be run by every Routine that calls it."""
        rc, out = run_main(model_check.main,
                           ["model_check", "rule-promotion", "--model",
                            "claude-haiku-4-5-20251001", "--effort", "low"])
        self.assertEqual(rc, 1)
        self.assertTrue(out.strip().startswith("!!"))

    def test_an_unknown_task_is_refused_rather_than_waved_through(self):
        rc, _ = run_main(model_check.main, ["model_check", "not-a-task"])
        self.assertEqual(rc, 1)


# ======================================================================
# netcheck — reachable is not usable
# ======================================================================
class FakeResponse:
    def __init__(self, body, status=200):
        self._b = body.encode()
        self.status = status

    def read(self, n=None):
        return self._b[:n] if n else self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class NetcheckTests(unittest.TestCase):

    def test_the_user_agent_carries_a_contact_and_names_this_agent(self):
        ua = netcheck.user_agent()
        self.assertIn("tradingagent-claude", ua)
        self.assertIn("@", ua)

    def test_the_user_agent_does_not_leak_the_owners_private_address(self):
        """The UA goes to every third-party data source on every request. The
        account owner chose a separate public contact for exactly this; a
        refactor that reached for the git identity or an env var holding their
        real address would broadcast it silently."""
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("TRADING_AGENT_CONTACT", None)
            self.assertNotIn("owner@example.invalid", netcheck.user_agent())
            self.assertEqual(netcheck.DEFAULT_CONTACT, "contact@set-via-env.invalid")

    def test_a_clean_200_is_reachable(self):
        with mock.patch.object(netcheck.urllib.request, "urlopen",
                               return_value=FakeResponse('{"is_open":true}')):
            ok, msg = netcheck.probe("example.com", "/")
        self.assertTrue(ok)
        self.assertIn("200", msg)

    def test_a_200_carrying_a_bot_challenge_is_degraded(self):
        """stooq.com does this. An allowlist entry that returns a challenge is
        worse than a blocked one, because it looks like it works."""
        body = "<html>Checking your browser before accessing</html>"
        with mock.patch.object(netcheck.urllib.request, "urlopen",
                               return_value=FakeResponse(body)):
            ok, msg = netcheck.probe("stooq.com", "/")
        self.assertFalse(ok)
        self.assertIn("DEGRADED", msg)

    def test_a_challenge_served_as_an_error_status_is_still_a_challenge(self):
        """reuters and marketwatch served their wall as a 401 and both read
        healthy, because the status was inspected and the body was not."""
        err = urllib.error.HTTPError(
            "https://x/", 401, "no", {},
            io.BytesIO(b"<html>cf-browser-verification</html>"))
        with mock.patch.object(netcheck.urllib.request, "urlopen",
                               side_effect=err):
            ok, msg = netcheck.probe("x.com", "/")
        self.assertFalse(ok)
        self.assertIn("DEGRADED", msg)

    def test_401_and_429_are_reachable_but_403_is_not(self):
        """401 means the network is open and a key is missing — the next
        problem, not this one. 403 on a public page is a WAF refusing us, and
        calling that ok is how bls.gov sat green while returning nothing."""
        for code, expect in ((401, True), (429, True), (403, False)):
            err = urllib.error.HTTPError("https://x/", code, "no", {},
                                         io.BytesIO(b"denied"))
            with mock.patch.object(netcheck.urllib.request, "urlopen",
                                   side_effect=err):
                ok, _ = netcheck.probe("x.com", "/")
            self.assertEqual(ok, expect, code)

    def test_a_blocked_connect_is_reported_as_the_proxy_not_the_host(self):
        err = urllib.error.URLError("Tunnel connection failed: 403 Forbidden")
        with mock.patch.object(netcheck.urllib.request, "urlopen",
                               side_effect=err):
            ok, msg = netcheck.probe("x.com", "/")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", msg)

    def test_the_allowlist_is_deduplicated_and_tier_scoped(self):
        req = netcheck.allowlist(["required"])
        self.assertEqual(len(req), len(set(req)))
        self.assertIn("paper-api.alpaca.markets", req)
        self.assertNotIn("api.coingecko.com", req)

    def test_every_required_host_is_one_alpaca_or_robinhood_actually_needs(self):
        """A host in the required tier blocks the whole day when it is down,
        so the tier is a claim about necessity, not a wish list."""
        for h in netcheck.allowlist(["required"]):
            self.assertTrue(h.endswith("alpaca.markets")
                            or h.endswith("robinhood.com"), h)


# ======================================================================
# smoke_submit — the one tool that deliberately sends a real order
# ======================================================================
class SmokeSubmitTests(unittest.TestCase):

    def test_the_test_limit_is_far_enough_below_the_market_to_never_fill(self):
        """The whole safety of the smoke test is that the order cannot fill.
        A discount that drifted toward 1.0 would turn a connectivity check
        into an unplanned position."""
        self.assertLessEqual(smoke_submit.UNFILLABLE_DISCOUNT, 0.90)
        self.assertGreater(smoke_submit.UNFILLABLE_DISCOUNT, 0.0)

    def test_the_price_prefers_the_last_trade_over_the_daily_bar(self):
        a = mock.Mock()
        a._request.return_value = {"F": {"latestTrade": {"p": 11.0},
                                         "dailyBar": {"c": 9.0}}}
        self.assertEqual(smoke_submit.last_price(a, "F"), 11.0)

    def test_a_missing_price_raises_rather_than_defaulting(self):
        """A zero or guessed price would size the test order off nothing."""
        a = mock.Mock()
        a._request.return_value = {"F": {}}
        with self.assertRaises(SystemExit):
            smoke_submit.last_price(a, "F")

    def test_it_refuses_to_run_unless_the_account_is_flat_and_the_market_open(self):
        a = mock.Mock()
        a.clock.return_value = {"is_open": False}
        with self.assertRaises(SystemExit):
            smoke_submit.check(a)

        a.clock.return_value = {"is_open": True}
        a.positions.return_value = [{"symbol": "DT"}]
        with self.assertRaises(SystemExit):
            smoke_submit.check(a)

        a.positions.return_value = []
        a.open_orders.return_value = [{"id": "1"}]
        with self.assertRaises(SystemExit):
            smoke_submit.check(a)

        a.open_orders.return_value = []
        self.assertIsNone(smoke_submit.check(a))

    def test_an_accepted_entry_with_no_protective_legs_is_called_out(self):
        a = mock.Mock()
        a.submit.return_value = {"id": "abc", "status": "accepted", "legs": []}
        _, out = run_main(lambda: smoke_submit.attempt(a, mock.Mock(), "t"))
        self.assertIn("NO PROTECTIVE LEGS", out)


# ======================================================================
# FRED — the macro numbers the brief quotes
# ======================================================================
class FredTests(unittest.TestCase):

    CSV = ("DATE,ICSA\n"
           "2026-09-01,220000\n"
           "2026-09-08,.\n"           # FRED writes an unreported value as "."
           "2026-09-15,231000\n")

    def test_a_missing_observation_is_dropped_not_read_as_zero(self):
        """Carrying "." through as 0.0 turns a gap in the data into a reading
        of zero. For a spread or a rate that is not a small error — it is a
        different market."""
        with mock.patch.object(fred, "_fetch", return_value=self.CSV):
            rows = fred.series("ICSA")
        self.assertEqual([v for _, v in rows], [220000.0, 231000.0])
        self.assertNotIn(0.0, [v for _, v in rows])

    def test_observations_come_back_oldest_first(self):
        with mock.patch.object(fred, "_fetch", return_value=self.CSV):
            rows = fred.series("ICSA")
        self.assertEqual([d for d, _ in rows], sorted(d for d, _ in rows))

    def test_latest_is_the_most_recent_observation(self):
        with mock.patch.object(fred, "_fetch", return_value=self.CSV):
            self.assertEqual(fred.latest("ICSA"), (dt.date(2026, 9, 15), 231000.0))

    def test_limit_keeps_the_newest_n(self):
        with mock.patch.object(fred, "_fetch", return_value=self.CSV):
            self.assertEqual(fred.series("ICSA", limit=1)[0][1], 231000.0)

    def test_an_all_empty_series_raises_instead_of_returning_nothing(self):
        """An empty list would read downstream as "no change"."""
        with mock.patch.object(fred, "_fetch", return_value="DATE,X\n2026-01-01,.\n"):
            with self.assertRaises(AdapterError):
                fred.series("X")

    def test_a_snapshot_records_the_error_and_keeps_going(self):
        """One dead series must not blank the whole macro block."""
        def boom(sid, timeout=30):
            if sid == "ICSA":
                raise AdapterError("down")
            return self.CSV
        with mock.patch.object(fred, "_fetch", side_effect=boom):
            snap = fred.snapshot(["ICSA", "DGS10"])
        self.assertIn("error", snap["ICSA"])
        self.assertIn("value", snap["DGS10"])

    def test_every_named_series_has_a_human_readable_name(self):
        """The brief cites "initial jobless claims", not "ICSA"."""
        for sid, name in fred.SERIES.items():
            self.assertTrue(name and name != sid, sid)


# ======================================================================
# the simulation's reporting layer
# ======================================================================
def result(final, **kw):
    r = SimResult(name="s", seed=1, starting_equity=300.0, final_equity=final)
    for k, v in kw.items():
        setattr(r, k, v)
    return r


class AggregateTests(unittest.TestCase):

    def test_ruin_is_counted_at_half_the_starting_equity(self):
        """docs/05 quotes this number. `ruined` is <= 50%, so 150 on 300 is
        ruin and 150.01 is not."""
        agg = run_suite.aggregate([result(150.0), result(150.01),
                                   result(400.0), result(400.0)])
        self.assertAlmostEqual(agg["pct_runs_ruined_50pct"], 0.25)

    def test_profitable_is_strictly_above_the_starting_equity(self):
        agg = run_suite.aggregate([result(300.0), result(301.0)])
        self.assertAlmostEqual(agg["pct_runs_profitable"], 0.5)

    def test_locked_runs_are_counted_separately_from_ruined_ones(self):
        """A locked account is not a ruined one — it stopped itself. Merging
        them was how the 5%/week experiment looked survivable."""
        agg = run_suite.aggregate([result(280.0, end_state="LOCKED"),
                                   result(290.0)])
        self.assertAlmostEqual(agg["pct_runs_locked"], 0.5)
        self.assertAlmostEqual(agg["pct_runs_ruined_50pct"], 0.0)

    def test_weekly_statistics_are_none_rather_than_zero_without_weeks(self):
        """0.0% of weeks over +5% and "we ran no weeks" are different claims."""
        agg = run_suite.aggregate([result(300.0)])
        self.assertIsNone(agg["mean_weekly_return"])
        self.assertIsNone(agg["pct_weeks_over_+5pct"])

    def test_the_worst_drawdown_is_the_worst_not_the_mean(self):
        agg = run_suite.aggregate([result(300.0, max_drawdown=0.05),
                                   result(300.0, max_drawdown=0.31)])
        self.assertAlmostEqual(agg["worst_max_drawdown"], 0.31)
        self.assertAlmostEqual(agg["mean_max_drawdown"], 0.18)

    def test_percentiles_do_not_index_off_the_end_on_a_small_sample(self):
        for n in range(1, 12):
            agg = run_suite.aggregate([result(300.0 + i) for i in range(n)])
            self.assertEqual(agg["runs"], n)

    def test_the_capital_sweep_starts_at_the_real_account_size(self):
        self.assertEqual(capital_sweep.LEVELS[0], 300)
        self.assertIn("option_swing", capital_sweep.STRATEGIES)


# ======================================================================
# design_doc — the spreadsheet handed to a human
# ======================================================================
class DesignDocTests(unittest.TestCase):

    TABLES = ("DECISIONS", "BUGS", "SYSTEMS")

    def test_every_row_has_exactly_as_many_cells_as_there_are_columns(self):
        """openpyxl appends whatever it is given. A row one cell short shifts
        every later column silently, and the sheet still opens."""
        for t in self.TABLES:
            cols = getattr(design_doc, f"{t}_COLS")
            for r in getattr(design_doc, t):
                self.assertEqual(len(r), len(cols), f"{t}: {r[0]}")

    def test_decision_and_bug_ids_are_unique(self):
        """Docs cite these by id — M-22, B-15, D-24. A duplicate makes a
        citation ambiguous, and the lessons file is full of them."""
        for t in ("DECISIONS", "BUGS"):
            ids = [r[0] for r in getattr(design_doc, t)]
            self.assertEqual(len(ids), len(set(ids)),
                             sorted(i for i in ids if ids.count(i) > 1))

    def test_no_cell_is_empty_where_the_column_is_the_point(self):
        for r in design_doc.DECISIONS:
            self.assertTrue(str(r[3]).strip(), r[0])      # Decision
            self.assertTrue(str(r[4]).strip(), r[0])      # Rationale
        for r in design_doc.BUGS:
            self.assertTrue(str(r[3]).strip(), r[0])      # Issue

    def test_no_system_row_carries_a_secret(self):
        """This file is committed and handed to people. Auth columns describe
        where a key lives; they must never hold one."""
        for r in design_doc.SYSTEMS:
            blob = " ".join(str(c) for c in r)
            for marker in ("PK", "sk-", "ghp_", "BEGIN PRIVATE KEY"):
                self.assertNotIn(marker, blob, r[0])


# ======================================================================
# a repo-wide invariant, because this one has bitten twice
# ======================================================================
class TestInvocationTests(unittest.TestCase):

    def test_nothing_in_the_repo_runs_the_suite_without_the_sandbox(self):
        """`unittest discover -s tests` imports test modules as top-level
        modules, so tests/__init__.py never runs and the suite writes to the
        REAL state/ directory. That is how a phantom BUY reached
        state/fills.jsonl on 2026-09-24. preflight_phase2 was still invoking
        it that way afterwards — the docs were fixed and the code was not — so
        the rule is enforced here rather than remembered.

        Scanning is done on whitespace-NORMALISED file contents, not on grep
        lines. The first version of this test read line by line and scored
        zero against a mutation that removed `-t .` from preflight, because
        that call is wrapped across two lines and the word `discover` sits on
        the first one. A guard that cannot see the code it guards is the same
        vacuous-pass shape it was written to catch.
        """
        # Two places name the wrong form on purpose, and both should keep
        # saying it. Listing them rather than silencing whole trees means a
        # NEW one still fails.
        prose = {
            "state/rehearsals/": "a dated record of what was actually run",
            "tests/test_state.py": "the guard test's docstring",
            "tests/test_reporting.py": "this test's own docstring",
        }
        files = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.yml",
                                "*.yaml"], cwd=ROOT, capture_output=True,
                               text=True).stdout.split()
        self.assertGreater(len(files), 20, "git ls-files found nothing")

        pat = re.compile(r"discover.{0,80}?-s[\s\",]+tests", re.S)
        offenders = []
        for rel in files:
            if any(rel.startswith(k) for k in prose):
                continue
            text = " ".join((ROOT / rel).read_text().split())
            for m in pat.finditer(text):
                window = text[m.start():m.end() + 24]
                if "-t" not in window[m.end() - m.start():]:
                    offenders.append(f"{rel}: ...{window}...")
        self.assertEqual(offenders, [], "run the suite with -t .:\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
