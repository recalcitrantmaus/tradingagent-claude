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

    def test_ambiguity_on_the_decision_line_resolves_conservatively(self):
        self.assertIs(parse("## Posture\nRISK_ON, or arguably NO_TRADE\n"),
                      Posture.NO_TRADE)

    def test_reasoning_below_the_decision_line_is_not_the_decision(self):
        """The real false negative this parser had to fix.

        A brief states its posture, then argues for it by naming the postures
        it rejected. Scanning the whole section read those as the decision and
        resolved to NO_TRADE — blocking a day the brief had cleared. Today's
        brief is exactly this shape.
        """
        text = ("## Posture\nRISK_OFF\n\n"
                "**Single reason:** conditions to cap risk, not to add it. "
                "This is not a NO_TRADE regime, and it is plainly not RISK_ON.\n"
                "## Watchlist\n")
        self.assertIs(parse(text), Posture.RISK_OFF)

    def test_preamble_without_a_token_is_skipped(self):
        self.assertIs(parse("## Posture\n\nSee below.\nRISK_ON + reason\n"),
                      Posture.RISK_ON)

    def test_section_with_no_token_at_all_fails_closed(self):
        self.assertIs(parse("## Posture\nmaybe tomorrow\n"), Posture.NO_TRADE)

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


# ---------------------------------------------------------------------------
# Submitting is not filling.
# ---------------------------------------------------------------------------
from adapters.base import OrderTicket
from engine.risk import OrderProposal as _OP
from tools.paper_session import fill_record


def _proposal():
    return _OP(symbol="XYZ", asset_class="equity", side="buy",
               price=10.00, stop=9.20, target=12.00, thesis="test")


def _ticket():
    return OrderTicket(symbol="XYZ", asset_class="equity", side="buy",
                       qty=7, limit_price=10.00, stop_price=9.20,
                       take_profit=12.00, thesis="test")


class TestOnlyRealFillsAreRecorded(unittest.TestCase):
    """The fill log is the input to measured expectancy and the option unlock.

    Anything written there that did not actually happen corrupts both, plus
    the entry price of the next real trade in that symbol via the FIFO pairing
    in closed_trades(). So the rule is narrow on purpose.
    """

    def test_a_working_order_writes_nothing(self):
        o = {"id": "abc", "status": "new", "filled_qty": 0,
             "filled_avg_price": None}
        self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))

    def test_an_accepted_but_unfilled_order_writes_nothing(self):
        for status in ("accepted", "pending_new", "held", "partially_filled"):
            with self.subTest(status=status):
                o = {"id": "abc", "status": status, "filled_qty": 0,
                     "filled_avg_price": None}
                self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))

    def test_a_rejected_order_writes_nothing(self):
        o = {"id": "abc", "status": "rejected", "filled_qty": 0,
             "filled_avg_price": None}
        self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))

    def test_a_fill_is_recorded_at_the_brokers_price_not_the_proposed_one(self):
        o = {"id": "abc", "status": "filled", "filled_qty": 7,
             "filled_avg_price": 10.043}
        row = fill_record(_proposal(), 7, _ticket(), o)
        self.assertIsNotNone(row)
        # 10.00 was the proposal. Recording it would understate slippage and
        # overstate every R this trade ever produces.
        self.assertEqual(row["price"], 10.043)
        self.assertEqual(row["qty"], 7)
        self.assertEqual(row["stop"], 9.20)
        self.assertFalse(row["dry_run"])
        self.assertEqual(row["order_id"], "abc")

    def test_a_partial_fill_records_only_the_part_that_filled(self):
        o = {"id": "abc", "status": "partially_filled", "filled_qty": 3,
             "filled_avg_price": 10.01}
        row = fill_record(_proposal(), 7, _ticket(), o)
        self.assertEqual(row["qty"], 3)      # not the 7 that was approved

    def test_a_zero_price_fill_is_not_trusted(self):
        # A filled_avg_price of 0 or None is a broker anomaly, not a free
        # share. Recording it would divide by zero in R and show infinite edge.
        for px in (0, None, ""):
            with self.subTest(px=px):
                o = {"id": "abc", "status": "filled", "filled_qty": 7,
                     "filled_avg_price": px}
                self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))

    def test_the_recorded_row_survives_closed_trades_pairing(self):
        from tools.review import closed_trades
        entry = fill_record(_proposal(), 7, _ticket(),
                            {"id": "a", "status": "filled", "filled_qty": 7,
                             "filled_avg_price": 10.00})
        entry["ts"] = "2026-03-02T10:00:00+00:00"
        exit_ = dict(entry, side="sell", price=11.60,
                     ts="2026-03-02T14:00:00+00:00")
        trades = closed_trades([entry, exit_])
        self.assertEqual(len(trades), 1)
        # risk = (10.00 - 9.20) * 7 = 5.60; pnl = 1.60 * 7 = 11.20 -> 2.0R
        self.assertAlmostEqual(trades[0]["R"], 2.0, places=6)


class TestAwaitFillSemantics(unittest.TestCase):
    def test_a_terminal_status_stops_polling_immediately(self):
        from adapters.alpaca import AlpacaAdapter
        calls = []

        class Stub(AlpacaAdapter):
            def __init__(self):
                pass
            def order(self, order_id):
                calls.append(order_id)
                return {"id": order_id, "status": "filled", "filled_qty": "7",
                        "filled_avg_price": "10.04"}

        o = Stub().await_fill("abc", seconds=30, interval=5)
        self.assertEqual(len(calls), 1)          # no sleeping on a done order
        self.assertTrue(o["resolved"])
        self.assertEqual(o["filled_qty"], 7.0)   # coerced from the string
        self.assertEqual(o["filled_avg_price"], 10.04)

    def test_an_order_that_never_resolves_is_reported_unresolved(self):
        from adapters.alpaca import AlpacaAdapter

        class Stub(AlpacaAdapter):
            def __init__(self):
                pass
            def order(self, order_id):
                return {"id": order_id, "status": "new", "filled_qty": "0",
                        "filled_avg_price": None}

        o = Stub().await_fill("abc", seconds=0, interval=0)
        self.assertFalse(o["resolved"])
        self.assertEqual(o["filled_qty"], 0.0)
        self.assertIsNone(o["filled_avg_price"])
        # and it earns no row
        self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))

    def test_the_dry_run_adapter_answers_the_same_interface(self):
        from adapters.alpaca import DryRunAlpaca
        o = DryRunAlpaca.await_fill(None, "abc")
        self.assertTrue(o["resolved"])
        self.assertIsNone(fill_record(_proposal(), 7, _ticket(), o))
