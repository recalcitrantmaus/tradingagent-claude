"""state.py holds the record of truth between sessions, and had no tests.

Every fill, every halt and every drawdown baseline passes through these four
functions. A container is reclaimed after every session, so the failure mode
they guard is not exotic — it is the default.
"""
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import state


class _Isolated(unittest.TestCase):
    """Never touch the real state/ directory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(state, "STATE", self.tmp),
            mock.patch.object(state, "LEDGER", self.tmp / "ledger.json"),
            mock.patch.object(state, "FILLS", self.tmp / "fills.jsonl"),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestARebornLedgerIsAnnounced(_Isolated):
    """A missing ledger is indistinguishable from a brand-new account, and the
    EMPTY defaults are deliberately benign: NORMAL, peak at the deposit, no
    halts, no fills. Correct on day one; dangerous on any day after it, because
    the session has silently discarded a halt, reset the peak the drawdown lock
    measures against, and forgotten every closed trade.
    """

    def test_a_missing_ledger_is_flagged_reborn(self):
        d = state.load()
        self.assertTrue(d.get("reborn"), "a reborn ledger must be detectable")
        self.assertEqual(d["risk_state"], "NORMAL")
        self.assertEqual(d["peak_equity"], 300.0)

    def test_a_reborn_ledger_says_so_on_stderr(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            state.load()
        msg = err.getvalue()
        self.assertIn("STOP", msg)
        self.assertIn("halt or drawdown history is gone", msg)

    def test_an_existing_ledger_is_NOT_flagged_reborn(self):
        state.save({"risk_state": "DAY_HALT", "peak_equity": 412.0})
        d = state.load()
        self.assertNotIn("reborn", d)
        self.assertEqual(d["risk_state"], "DAY_HALT")
        self.assertEqual(d["peak_equity"], 412.0)

    def test_a_halt_survives_a_round_trip(self):
        # The property that matters: a session cannot lose a halt by restarting.
        state.save({"risk_state": "LOCKED", "halts": [{"why": "-20%"}],
                    "peak_equity": 500.0})
        d = state.load()
        self.assertEqual(d["risk_state"], "LOCKED")
        self.assertEqual(len(d["halts"]), 1)

    def test_load_creates_the_file_so_the_next_load_is_not_also_reborn(self):
        state.load()
        self.assertTrue((self.tmp / "ledger.json").exists())
        self.assertNotIn("reborn", state.load())

    def test_the_reborn_flag_is_not_persisted(self):
        # Otherwise every subsequent load would look reborn forever.
        state.load()
        self.assertNotIn("reborn", json.loads((self.tmp / "ledger.json").read_text()))


class TestFillsAreAppendOnly(_Isolated):
    """JSONL because parallel sessions merge cleanly; a JSON blob conflicts."""

    def test_a_fill_round_trips(self):
        state.append_fill({"symbol": "DT", "side": "buy", "qty": 1.0,
                           "price": 58.47})
        rows = state.read_fills()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "DT")

    def test_a_timestamp_is_added_when_absent(self):
        state.append_fill({"symbol": "DT", "side": "buy", "qty": 1.0,
                           "price": 58.47})
        ts = state.read_fills()[0]["ts"]
        dt.datetime.fromisoformat(ts)          # parses, or this raises

    def test_a_supplied_timestamp_is_preserved(self):
        # The broker's time, not ours: a fill recovered from the broker feed
        # carries the moment it actually happened.
        state.append_fill({"symbol": "DT", "side": "buy", "qty": 1.0,
                           "price": 58.47, "ts": "2026-09-23T14:04:57Z"})
        self.assertEqual(state.read_fills()[0]["ts"], "2026-09-23T14:04:57Z")

    def test_appending_never_rewrites_earlier_rows(self):
        for i in range(3):
            state.append_fill({"symbol": f"S{i}", "side": "buy", "qty": 1.0,
                               "price": 10.0 + i})
        rows = state.read_fills()
        self.assertEqual([r["symbol"] for r in rows], ["S0", "S1", "S2"])

    def test_no_fills_file_is_empty_not_an_error(self):
        self.assertEqual(state.read_fills(), [])

    def test_blank_lines_are_tolerated(self):
        state.append_fill({"symbol": "DT", "side": "buy", "qty": 1.0, "price": 1.0})
        with (self.tmp / "fills.jsonl").open("a") as fh:
            fh.write("\n\n")
        self.assertEqual(len(state.read_fills()), 1)

    def test_the_ledger_is_written_deterministically(self):
        # sort_keys, so two sessions writing the same state produce the same
        # bytes and git does not show a spurious diff.
        state.save({"b": 2, "a": 1})
        first = (self.tmp / "ledger.json").read_text()
        state.save({"a": 1, "b": 2})
        self.assertEqual(first, (self.tmp / "ledger.json").read_text())
