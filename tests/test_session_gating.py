"""The runner must feed the risk engine the book it is building.

Found 2026-09-23, live, with the market open. `RiskOfficer.evaluate` reads
BOTH the concurrency taper (`correlated_risk_decay ** len(portfolio.positions)`)
and the T-1 aggregate open-risk cap (`portfolio.open_risk`) out of the
portfolio it is handed. `tools.paper_session` handed it the same untouched
portfolio for every proposal in the session, so every proposal was gated as
though it were the first one: the taper never tapered, and the 4% book cap
never bound.

Both controls exist in `engine/` and both are unit-tested there. Neither was
reachable from the only path that actually sends orders. That is T-1's own
failure mode one layer up — the control landed in the engine and was never
wired into the caller — and no engine-level test could see it, because from
inside the engine both controls work perfectly.

These tests drive the real `main()` loop. They do not inspect its source.
"""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import paper_session


BRIEF = "# brief\n## Posture\nNEUTRAL — a reason\n"


class FakeAdapter:
    """Enough broker to drive the loop; sends nothing."""

    def __init__(self, equity=300.0, positions=None, stops=None):
        self._eq = equity
        self.submitted = []
        self._positions = positions or []
        self.stops = stops or {}

    def account(self):
        return {"equity": self._eq, "cash": self._eq, "buying_power": self._eq,
                "daytrade_count": 0, "pattern_day_trader": False,
                "trading_blocked": False}

    def positions(self):
        return list(self._positions)

    def positions_without_stops(self):
        return []

    def resting_stops(self):
        return dict(self.stops)

    def submit(self, ticket):
        self.submitted.append(ticket)
        return {"dry_run": True}


class FakeState:
    def __init__(self):
        self.fills = []
        self.ledger = {"peak_equity": 300.0}

    def load(self):
        return self.ledger

    def save(self, led=None):
        pass

    def read_fills(self):
        return []

    def append_fill(self, row):
        self.fills.append(row)


def run_session(proposals, equity=300.0, positions=None, stops=None):
    """Run the real gating loop over `proposals`. Returns (adapter, printed)."""
    today = dt.date.today()
    adapter = FakeAdapter(equity, positions, stops)
    fake_state = FakeState()
    with tempfile.TemporaryDirectory() as td:
        plans, briefs = Path(td) / "plans", Path(td) / "briefs"
        plans.mkdir(), briefs.mkdir()
        (plans / f"{today.isoformat()}.json").write_text(json.dumps(proposals))
        (briefs / f"{today.isoformat()}.md").write_text(BRIEF)
        out = []
        with mock.patch.object(paper_session, "PLAN_DIR", plans), \
             mock.patch.object(paper_session, "BRIEF_DIR", briefs), \
             mock.patch.object(paper_session, "DryRunAlpaca", lambda: adapter), \
             mock.patch.object(paper_session, "state", fake_state), \
             mock.patch.object(paper_session, "closed_trades", lambda _f: []), \
             mock.patch.object(sys, "argv", ["paper_session", "--dry-run"]), \
             mock.patch("builtins.print", lambda *a, **k: out.append(
                 " ".join(str(x) for x in a))):
            paper_session.main()
    return adapter, "\n".join(out)


class TestTaperBindsWithinOneSession(unittest.TestCase):
    """The exact pair that exposed this, live, on 2026-09-23."""

    PROPOSALS = [
        {"symbol": "AAA", "asset_class": "equity", "side": "buy",
         "price": 58.47, "stop": 55.80, "target": 63.81, "thesis": "first"},
        {"symbol": "BBB", "asset_class": "equity", "side": "buy",
         "price": 72.53, "stop": 67.42, "target": 82.74, "thesis": "second"},
    ]

    def test_second_proposal_is_refused_on_the_tapered_budget(self):
        """BBB risks $5.11/share. Position 2's budget is 1% of $300 = $3.00.

        It fits the untapered 2% budget ($6.00) and does not fit the tapered
        one, so it is approved if and only if the taper is inert. Before the
        fix this order was APPROVED at 1.70% of equity.
        """
        adapter, out = run_session(self.PROPOSALS)
        sent = [t.symbol for t in adapter.submitted]
        self.assertEqual(sent, ["AAA"],
                         f"BBB should not have been sent. Got {sent}\n{out}")
        self.assertIn("REJECT BBB", out)
        self.assertIn("tapered to 1.00% as position 2", out)

    def test_the_first_proposal_still_gets_the_full_budget(self):
        """The fix must not quietly shrink position 1."""
        adapter, out = run_session(self.PROPOSALS)
        self.assertEqual(adapter.submitted[0].qty, 1)
        self.assertIn("APPROVE AAA", out)

    def test_order_decides_which_one_lives(self):
        """Reversed, the cheap-risk name fits position 2 and BOTH are taken.

        This is not a defect; it is why the plan must fix its ordering on
        conviction BEFORE the engine is run, and say so.
        """
        adapter, _ = run_session(list(reversed(self.PROPOSALS)))
        self.assertEqual([t.symbol for t in adapter.submitted], ["BBB", "AAA"])


class TestARefusalNamesTheConstraintThatBound(unittest.TestCase):
    """Found while fixing the taper, 2026-09-23.

    `Decision.reject` APPENDS the binding constraint to `reasons`, and
    `evaluate` appends informational notes before it — the expected-R grade
    among them. The runner printed `reasons[0]`, so a refusal reported
    whichever note landed first. The live case: BBB refused on the tapered
    risk budget and logged as "expected R 2.00", a passing grade, as though
    the reward-to-risk gate had turned it away.

    This routine's instruction is that a refusal nobody can check is not a
    decision. A refusal naming the wrong control is worse — it reads as a
    record while pointing somewhere else.
    """

    def test_the_logged_reason_is_the_binding_constraint(self):
        adapter, out = run_session([
            {"symbol": "AAA", "asset_class": "equity", "side": "buy",
             "price": 58.47, "stop": 55.80, "target": 63.81, "thesis": "1st"},
            {"symbol": "BBB", "asset_class": "equity", "side": "buy",
             "price": 72.53, "stop": 67.42, "target": 82.74, "thesis": "2nd"},
        ])
        line = next(l for l in out.splitlines() if "REJECT BBB" in l)
        self.assertIn("tapered to 1.00% as position 2", line)
        self.assertNotIn("expected R", line)

    def test_an_informational_note_is_never_reported_as_a_refusal(self):
        """A target far too close: the expected-R gate is the real reason."""
        adapter, out = run_session([
            {"symbol": "AAA", "asset_class": "equity", "side": "buy",
             "price": 50.00, "stop": 45.00, "target": 51.00, "thesis": "thin"},
        ])
        line = next(l for l in out.splitlines() if "REJECT AAA" in l)
        self.assertIn("expected R", line)
        self.assertEqual(adapter.submitted, [])


class TestAggregateOpenRiskCapBindsWithinOneSession(unittest.TestCase):
    """T-1's cap, on the path that actually sends orders."""

    def test_four_proposals_cannot_exceed_the_four_percent_book(self):
        """Four names at $10 risking $0.60/share.

        Ungated by the taper each takes 7 shares (the 25% single-position cap)
        for $4.20 of risk apiece — $16.80, or 5.6% of a $300 book, past the 4%
        cap and past the daily halt. The engine refuses that only if the runner
        tells it what it has already committed.
        """
        props = [{"symbol": s, "asset_class": "equity", "side": "buy",
                  "price": 10.0, "stop": 9.40, "target": 11.80, "thesis": s}
                 for s in ("AAA", "BBB", "CCC", "DDD")]
        adapter, out = run_session(props)
        risk = sum(t.qty * (10.0 - 9.40) for t in adapter.submitted)
        self.assertLessEqual(
            round(risk, 2), 0.04 * 300.0,
            f"book carries ${risk:.2f} at risk, over the 4% cap\n{out}")

    def test_a_single_position_still_gets_through(self):
        """A cap that refuses everything is not a cap, it is an outage."""
        adapter, _ = run_session(
            [{"symbol": "AAA", "asset_class": "equity", "side": "buy",
              "price": 10.0, "stop": 9.40, "target": 11.80, "thesis": "x"}])
        self.assertEqual(len(adapter.submitted), 1)
        self.assertGreater(adapter.submitted[0].qty, 0)


class TestCarriedPositionsKeepTheirStops(unittest.TestCase):
    """A stop resting at the broker must reach `Portfolio.open_risk`.

    Found 2026-09-23 while reasoning forward about the DT order resting at the
    broker. The runner rebuilt broker positions with `stop=None`, and
    `open_risk` counts an unstopped position at FULL NOTIONAL — by design,
    since an unstopped loss is unbounded. So one carried $58 position on a
    $300 account reported ~19% of equity at risk against a 4% cap, and every
    entry the next session would have been refused on the aggregate cap.

    That failure is conservative in direction and therefore easy to mistake
    for the guardrail working. It is not: it is an outage wearing a guardrail's
    error message.
    """

    HELD = [{"symbol": "ZZZ", "qty": 1.0, "avg_price": 58.47,
             "market_value": 58.47, "unrealized_pl": 0.0}]
    NEW = [{"symbol": "AAA", "asset_class": "equity", "side": "buy",
            "price": 10.0, "stop": 9.40, "target": 11.80, "thesis": "x"}]

    def test_a_stopped_carry_leaves_room_for_a_new_entry(self):
        """ZZZ stopped at 55.80 risks $2.67, not $58.47. Room remains."""
        adapter, out = run_session(self.NEW, positions=self.HELD,
                                   stops={"ZZZ": 55.80})
        self.assertEqual(len(adapter.submitted), 1,
                         f"a stopped carry should not freeze the book\n{out}")

    def test_an_unstopped_carry_still_consumes_the_whole_book(self):
        """The conservative rule must survive the fix, not be softened by it.

        No stop known for ZZZ means its loss really is unbounded, and the 4%
        cap should refuse the next entry. This is the case the old code was
        accidentally right about, and it has to stay right.
        """
        adapter, out = run_session(self.NEW, positions=self.HELD, stops={})
        self.assertEqual(adapter.submitted, [])
        self.assertIn("portfolio open-risk cap", out)


if __name__ == "__main__":
    unittest.main()
