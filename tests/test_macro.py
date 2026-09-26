import contextlib
import io
import json
import unittest

from tools import macro


class MacroTest(unittest.TestCase):
    def test_prints_the_snapshot_as_json(self):
        snap = {"DGS10": {"value": 4.1, "as_of": "2026-09-25", "stale_days": 1}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = macro.main(fetch=lambda: snap)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue()), snap)


if __name__ == "__main__":
    unittest.main()
