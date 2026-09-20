"""Durable account state. The ledger on disk is the record of truth between
sessions; the broker is the record of truth about reality. They must agree.
"""
from pathlib import Path
from typing import Dict, Any
import datetime as dt
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
LEDGER = STATE / "ledger.json"
FILLS = STATE / "fills.jsonl"

EMPTY: Dict[str, Any] = {
    "mode": "paper",
    "phase": "phase2",
    "week_start_equity": 300.0,
    "day_start_equity": 300.0,
    "days": [],                  # one record per trading day
    "halts": [],                 # every circuit-breaker transition, with cause
    "starting_equity": 300.0,
    "cash": 300.0,
    "positions": {},
    "realized_pnl": 0.0,
    "peak_equity": 300.0,
    "equity_curve": [],
    "risk_state": "NORMAL",
    "day_trades": [],
    "human_authorization": None,
    "last_reconciled": None,
    # The cash invariant's anchor. `cash` above was written once at birth and
    # never again, so reconcile() had nothing to compare against and a broker
    # cash change with no position change passed silently (2026-09-18).
    # These are re-anchored at every open and close.
    "broker_cash": None,
    "broker_equity": None,
    "broker_cash_at": None,
    "reconcile_drift": [],
}


def load() -> Dict[str, Any]:
    """The ledger, or a fresh one — loudly.

    A missing ledger is indistinguishable from a brand-new account, and the
    EMPTY defaults are deliberately benign: risk_state NORMAL, peak_equity at
    the starting deposit, no halts, no fills. That is correct on day one and
    dangerous on any day after it, because a session that starts from a
    reborn ledger has silently discarded a halt, reset the peak the drawdown
    lock measures against, and forgotten every closed trade. Fresh containers
    make this the default failure, not an exotic one, so it is announced.
    """
    if not LEDGER.exists():
        print("!! no state/ledger.json — starting from EMPTY defaults. "
              "risk_state=NORMAL, peak_equity=300, no fills. If this account "
              "has traded before, STOP: the ledger did not survive the "
              "session and any halt or drawdown history is gone.",
              file=sys.stderr)
        save(EMPTY)
        d = json.loads(json.dumps(EMPTY))
        d["reborn"] = True
        return d
    return json.loads(LEDGER.read_text())


def save(d: Dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, indent=2, sort_keys=True))


def append_fill(record: Dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", dt.datetime.now(dt.timezone.utc).isoformat())
    with FILLS.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def read_fills():
    if not FILLS.exists():
        return []
    return [json.loads(l) for l in FILLS.read_text().splitlines() if l.strip()]
