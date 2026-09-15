"""Durable account state. The ledger on disk is the record of truth between
sessions; the broker is the record of truth about reality. They must agree.
"""
from pathlib import Path
from typing import Dict, Any
import datetime as dt
import json

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
}


def load() -> Dict[str, Any]:
    if not LEDGER.exists():
        save(EMPTY)
        return json.loads(json.dumps(EMPTY))
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
