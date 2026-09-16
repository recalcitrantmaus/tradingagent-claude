"""Three controls that were prose, coincidence, or missing until 2026-09-16.

Found by the day-1 dry-run rehearsal (state/rehearsals/2026-09-16.md). Each
one could let an order reach the broker that the agent had already decided
against, or corrupt the record that decides when options unlock.
"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.posture import Posture, parse, limits_for, for_date
from tools.review import closed_trades


class TestPostureParsing(unittest.TestCase):
    def test_reads_the_posture_section(self):
        for token in ("RISK_ON", "NEUTRAL", "RISK_OFF", "NO_TRADE"):
            with self.subTest(token=token):
                self.assertIs(parse(f"## Posture\n{token} + a reason\n"),
                              Posture[token])

    def test_prose_elsewhere_does_not_decide_the_posture(self):
        """A brief discusses posture in prose; only the section is binding."""
        text = ("Intro: this is a reason to downgrade posture.\n"
                "## Posture\nRISK_ON — the single reason\n"
                "## Watchlist\nNo entry is authorised while posture is NO_TRADE.\n")
        self.assertIs(parse(text), Posture.RISK_ON)

    def test_ambiguity_inside_the_section_resolves_conservatively(self):
        self.assertIs(parse("## Posture\nRISK_ON, or arguably NO_TRADE\n"),
                      Posture.NO_TRADE)

    def test_unparseable_and_empty_fail_closed(self):
        for text in ("", "no heading here at all", "## Posture\nmaybe?\n"):
            with self.subTest(text=text[:20]):
                self.assertIs(parse(text), Posture.NO_TRADE)

    def test_missing_brief_is_no_trade(self):
        with tempfile.TemporaryDirectory() as d:
            p, why = for_date(Path(d), dt.date(2026, 9, 16))
            self.assertIs(p, Posture.NO_TRADE)
            self.assertIn("no brief", why)


class TestPostureLimits(unittest.TestCase):
    def test_no_trade_forbids_new_risk(self):
        self.assertFalse(limits_for(Posture.NO_TRADE).allows_new_risk)

    def test_risk_off_caps_risk_and_positions(self):
        lim = limits_for(Posture.RISK_OFF)
        self.assertTrue(lim.allows_new_risk)
        self.assertEqual(lim.max_risk_per_trade_pct, 0.01)
        self.assertEqual(lim.max_concurrent_positions, 1)

    def test_risk_on_uses_configured_defaults(self):
        lim = limits_for(Posture.RISK_ON)
        self.assertTrue(lim.allows_new_risk)
        self.assertIsNone(lim.max_risk_per_trade_pct)


class TestEmptyPlanIsBinding(unittest.TestCase):
    """An empty plan is a decision, not an absence of one."""

    def _plan_dir(self, write):
        from tools import paper_session
        d = Path(tempfile.mkdtemp())
        saved = paper_session.PLAN_DIR
        paper_session.PLAN_DIR = d
        if write is not None:
            (d / "2026-09-16.json").write_text(write)
        return paper_session, saved

    def test_absent_plan_returns_none_so_mechanical_may_run(self):
        ps, saved = self._plan_dir(None)
        try:
            self.assertIsNone(ps.propose_from_plan(dt.date(2026, 9, 16)))
        finally:
            ps.PLAN_DIR = saved

    def test_empty_plan_returns_empty_list_not_none(self):
        ps, saved = self._plan_dir("[]")
        try:
            out = ps.propose_from_plan(dt.date(2026, 9, 16))
            self.assertEqual(out, [])
            self.assertIsNotNone(
                out, "[] and None must stay distinguishable: `plan or "
                     "mechanical()` discarded a written refusal")
        finally:
            ps.PLAN_DIR = saved


class TestDryRunFillsNeverCount(unittest.TestCase):
    """Previewed tickets must not accrue toward expectancy or the option gate."""

    def _fill(self, **kw):
        d = dict(symbol="F", side="buy", qty=10, price=10.0, stop=9.0,
                 fees=0.0, multiplier=1, ts="2026-09-16T14:00:00Z")
        d.update(kw)
        return d

    def test_dry_run_round_trip_produces_no_closed_trade(self):
        fills = [self._fill(dry_run=True),
                 self._fill(side="sell", price=12.0, dry_run=True)]
        self.assertEqual(closed_trades(fills), [])

    def test_real_round_trip_still_counts(self):
        fills = [self._fill(), self._fill(side="sell", price=12.0)]
        self.assertEqual(len(closed_trades(fills)), 1)

    def test_phantom_dry_run_entry_cannot_corrupt_a_real_trade(self):
        """The FIFO head is where this does its damage.

        A dry-run entry at a fictional price sits first in the queue and pairs
        against the next REAL sell, rewriting that real trade's entry and R.
        """
        fills = [self._fill(price=1.0, dry_run=True),   # phantom, absurd price
                 self._fill(price=10.0),                # the real entry
                 self._fill(side="sell", price=12.0)]   # the real exit
        trades = closed_trades(fills)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["pnl"], 20.0,
                               msg="paired against the phantom entry")
        self.assertAlmostEqual(trades[0]["R"], 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
