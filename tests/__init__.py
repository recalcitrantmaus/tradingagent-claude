"""Package init — and a safety rail for the trading ledger.

On 2026-09-24 a test called `tools.trading_day.post_broker_fills` without
mocking `state.append_fill`, and wrote a phantom BUY of 1 DT @ 58.47 into the
REAL `state/fills.jsonl`, carrying `dry_run: False` and a fabricated
activity_id. `closed_trades` would have paired it as a genuine open lot and
corrupted the entry price and R of the next real DT trade — precisely the
damage that function's own docstring warns about for dry-run rows, arriving
through the test suite instead.

It passed the first time and failed the second, because by then it could see
its own row. That is the only reason it was noticed at all.

So the whole suite runs against a throwaway state directory. A test that wants
the real one has to say so, and none currently does. This costs nothing and
removes an entire class of accident: no test can corrupt the account's record
of what it traded.
"""
import atexit
import shutil
import tempfile
from pathlib import Path

from tools import state as _state

_SANDBOX = Path(tempfile.mkdtemp(prefix="tradingagent-tests-"))
atexit.register(shutil.rmtree, _SANDBOX, True)

_REAL = {"STATE": _state.STATE, "LEDGER": _state.LEDGER, "FILLS": _state.FILLS}

_state.STATE = _SANDBOX
_state.LEDGER = _SANDBOX / "ledger.json"
_state.FILLS = _SANDBOX / "fills.jsonl"


def real_state_paths():
    """The genuine paths, for a test that deliberately wants them."""
    return dict(_REAL)
