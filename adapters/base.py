"""Adapter interface and the authorization gate that guards live trading."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH_FILE = ROOT / "state" / "authorization.json"


class AdapterError(RuntimeError):
    pass


@dataclass
class Authorization:
    """A human's dated, explicit consent to send real orders.

    Deliberately awkward: it expires daily. An agent that has been running
    unattended for a week cannot still be trading on last Monday's consent.
    """
    granted_by: str
    granted_on: dt.date
    note: str
    max_order_notional: float

    @classmethod
    def load(cls) -> Optional["Authorization"]:
        if not AUTH_FILE.exists():
            return None
        d = json.loads(AUTH_FILE.read_text())
        return cls(granted_by=d["granted_by"],
                   granted_on=dt.date.fromisoformat(d["granted_on"]),
                   note=d["note"],
                   max_order_notional=float(d["max_order_notional"]))

    def valid_for(self, today: dt.date, notional: float) -> tuple[bool, str]:
        if self.granted_on != today:
            return False, (f"authorization is dated {self.granted_on}, today is "
                           f"{today}; live trading requires same-day consent")
        if notional > self.max_order_notional:
            return False, (f"order notional {notional:.2f} exceeds the authorized "
                           f"ceiling {self.max_order_notional:.2f}")
        return True, f"authorized by {self.granted_by}: {self.note}"


@dataclass
class OrderTicket:
    """What the adapter would send. Printable, reviewable, diffable."""
    symbol: str
    asset_class: str
    side: str
    qty: float
    limit_price: float
    stop_price: float
    take_profit: Optional[float] = None
    time_in_force: str = "day"
    thesis: str = ""

    def human(self) -> str:
        tp = f", target {self.take_profit:.2f}" if self.take_profit else ""
        return (f"{self.side.upper()} {self.qty:g} {self.symbol} "
                f"limit {self.limit_price:.2f}, stop {self.stop_price:.2f}{tp} "
                f"[{self.time_in_force}] — {self.thesis}")


class BrokerAdapter(Protocol):
    name: str
    live: bool

    def clock(self) -> Dict: ...
    def account(self) -> Dict: ...
    def positions(self) -> List[Dict]: ...
    def bars(self, symbol: str, limit: int = 250) -> List[Dict]: ...
    def submit(self, ticket: OrderTicket) -> Dict: ...
    def cancel_all(self) -> Dict: ...
