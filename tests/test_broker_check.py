import unittest

from tools import broker_check


class FakeAdapter:
    def __init__(self, positions=(), orders=(), unprotected=()):
        self._positions = list(positions)
        self._orders = list(orders)
        self._unprotected = list(unprotected)
        self.writes = 0

    def account(self):
        return {"equity": "299.62", "cash": "299.62"}

    def positions(self):
        return self._positions

    def open_orders(self, nested=False):
        return self._orders

    def resting_stops(self):
        return {}

    def positions_without_stops(self):
        return self._unprotected

    # Any write the tool made would land here.
    def submit(self, *a, **k):
        self.writes += 1

    def cancel_all(self):
        self.writes += 1

    def close_position(self, *a):
        self.writes += 1


class BrokerCheckTest(unittest.TestCase):
    def test_flat_account_reports_none_and_nothing_unprotected(self):
        lines, unprotected = broker_check.report(FakeAdapter())
        self.assertEqual(unprotected, [])
        self.assertIn("positions   : none", lines)
        self.assertIn("orders      : none", lines)

    def test_unprotected_position_is_returned(self):
        a = FakeAdapter(positions=[{"symbol": "DT", "qty": "1"}],
                        unprotected=["DT"])
        _, unprotected = broker_check.report(a)
        self.assertEqual(unprotected, ["DT"])

    def test_orders_carry_tif_and_status(self):
        a = FakeAdapter(orders=[{"symbol": "DT", "side": "sell", "type": "stop",
                                 "time_in_force": "gtc", "status": "held"}])
        lines, _ = broker_check.report(a)
        self.assertIn("('DT', 'sell', 'stop', 'gtc', 'held')", "\n".join(lines))

    def test_report_never_writes(self):
        a = FakeAdapter(positions=[{"symbol": "DT"}], unprotected=["DT"])
        broker_check.report(a)
        self.assertEqual(a.writes, 0)


if __name__ == "__main__":
    unittest.main()
