"""PaperBroker charges the frictions. A $300 account is destroyed by costs long
before it is destroyed by bad opinions, and none of this was tested.

Every number the simulation reports — every median, every ruin rate, the whole
evidence base in docs/05 and docs/04 — is produced through these functions. If
`fill_price` is wrong in the optimistic direction, the guardrails were validated
against a market that is kinder than the real one.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.broker import PaperBroker
from engine.config import DEFAULT
from engine.portfolio import Portfolio
from engine.risk import Decision, OrderProposal

TS = dt.datetime(2026, 9, 24, 14, 0, tzinfo=dt.timezone.utc)


def _prop(symbol="DT", cls="equity", side="buy", price=60.0, mult=1):
    return OrderProposal(symbol=symbol, asset_class=cls, side=side,
                         price=price, stop=54.0, target=78.0,
                         thesis="t", multiplier=mult)


class TestFrictionAlwaysCostsTheAccount(unittest.TestCase):
    """The sign is the whole point: a buy fills ABOVE the quote and a sell
    BELOW it. A friction model that got the sign wrong would pay the account
    to trade, and the simulator would have reported an edge that is pure
    bookkeeping."""

    def setUp(self):
        self.b = PaperBroker(Portfolio(300.0), DEFAULT)

    def test_an_equity_buy_fills_above_the_quote(self):
        self.assertGreater(self.b.fill_price(60.0, "equity", "buy"), 60.0)

    def test_an_equity_sell_fills_below_the_quote(self):
        self.assertLess(self.b.fill_price(60.0, "equity", "sell"), 60.0)

    def test_a_round_trip_at_an_unchanged_price_LOSES_money(self):
        buy = self.b.fill_price(60.0, "equity", "buy")
        sell = self.b.fill_price(60.0, "equity", "sell")
        self.assertLess(sell, buy, "a flat round trip must cost, not pay")

    def test_crypto_pays_a_wider_spread_than_equity(self):
        eq = self.b.fill_price(60.0, "equity", "buy") - 60.0
        cr = self.b.fill_price(60.0, "crypto", "buy") - 60.0
        self.assertGreater(cr, eq)

    def test_an_option_fill_never_goes_negative(self):
        # A penny option minus per-contract slippage would price below zero.
        self.assertGreaterEqual(self.b.fill_price(0.01, "option", "sell"), 0.01)

    def test_option_fees_scale_with_contracts_and_equity_pays_none(self):
        self.assertAlmostEqual(self.b.fees("option", 3),
                               3 * DEFAULT.option_contract_fee)
        self.assertEqual(self.b.fees("equity", 100), 0.0)


class TestExecutionRespectsTheDecision(unittest.TestCase):
    def setUp(self):
        self.pf = Portfolio(300.0)
        self.b = PaperBroker(self.pf, DEFAULT)

    def test_a_refused_decision_never_reaches_the_book(self):
        d = Decision(approved=False)
        self.assertIsNone(self.b.execute(TS, _prop(), d))
        self.assertEqual(self.pf.positions, {})

    def test_a_zero_quantity_never_reaches_the_book(self):
        d = Decision(approved=True)
        d.qty = 0.0
        self.assertIsNone(self.b.execute(TS, _prop(), d))
        self.assertEqual(self.pf.positions, {})

    def test_an_approved_order_opens_a_position_carrying_its_stop(self):
        d = Decision(approved=True)
        d.qty = 2.0
        self.b.execute(TS, _prop(), d)
        pos = self.pf.positions["DT"]
        self.assertEqual(pos.qty, 2.0)
        self.assertEqual(pos.stop, 54.0)      # or open_risk counts full notional
        self.assertGreater(pos.avg_price, 60.0)   # friction, not the quote

    def test_size_is_shaved_rather_than_failed_when_friction_bites(self):
        # Frictions move the price against us after sizing; the documented
        # behaviour is to shave, not to abandon the trade.
        pf = Portfolio(121.0)
        b = PaperBroker(pf, DEFAULT)
        d = Decision(approved=True)
        d.qty = 3.0                            # 3 x ~60 = 180 > 121 cash
        b.execute(TS, _prop(), d)
        self.assertEqual(pf.positions["DT"].qty, 2.0)
        self.assertGreaterEqual(pf.cash, 0.0)

    def test_an_unaffordable_order_is_abandoned_not_forced(self):
        pf = Portfolio(10.0)
        b = PaperBroker(pf, DEFAULT)
        d = Decision(approved=True)
        d.qty = 1.0
        self.assertIsNone(b.execute(TS, _prop(), d))
        self.assertEqual(pf.positions, {})
        self.assertEqual(pf.cash, 10.0)

    def test_cash_never_goes_negative_on_execution(self):
        pf = Portfolio(65.0)
        b = PaperBroker(pf, DEFAULT)
        d = Decision(approved=True)
        d.qty = 1.0
        b.execute(TS, _prop(), d)
        self.assertGreaterEqual(pf.cash, 0.0)


class TestClosingRealisesTheRightNumber(unittest.TestCase):
    def setUp(self):
        self.pf = Portfolio(300.0)
        self.b = PaperBroker(self.pf, DEFAULT)
        d = Decision(approved=True)
        d.qty = 2.0
        self.b.execute(TS, _prop(), d)

    def test_a_flat_exit_realises_a_LOSS_because_of_friction(self):
        _, pnl = self.b.close(TS, "DT", 60.0, reason="flat")
        self.assertLess(pnl, 0.0)

    def test_a_partial_close_leaves_the_rest_on_the_book(self):
        self.b.close(TS, "DT", 60.0, reason="scale-out", qty=1.0)
        self.assertEqual(self.pf.positions["DT"].qty, 1.0)

    def test_closing_more_than_held_closes_only_what_is_held(self):
        # Never sell short: this account has no short permission at all.
        self.b.close(TS, "DT", 60.0, reason="exit", qty=99.0)
        self.assertNotIn("DT", self.pf.positions)
        self.assertGreaterEqual(self.pf.cash, 0.0)

    def test_a_winning_exit_realises_a_gain_net_of_friction(self):
        _, pnl = self.b.close(TS, "DT", 78.0, reason="target")
        self.assertGreater(pnl, 0.0)
        gross = 2 * (78.0 - 60.0)
        self.assertLess(pnl, gross, "friction must be deducted from the gross")
