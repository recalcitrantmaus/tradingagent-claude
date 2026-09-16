"""The brief's posture, as code rather than prose.

`premarket-brief` emits a `Posture` the skill calls binding: `RISK_OFF` caps
new risk at 1% per trade and one position, `NO_TRADE` means no entries at all.
Until this module existed, nothing read it. The posture was enforced only by
the model's own compliance, which puts it on the wrong side of the one rule
that outranks everything: the model decides what to trade, code decides
whether it is allowed.

Everything here fails closed. A missing brief, an unreadable brief, or a
posture that cannot be parsed all resolve to NO_TRADE. A session that cannot
establish what today's posture is has not earned the right to open risk, and
the cost of being wrong in that direction is one missed day.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import datetime as dt
import re


class Posture(Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"
    NO_TRADE = "NO_TRADE"


# Most conservative first. Ties and ambiguity resolve toward the top.
_SEVERITY = [Posture.NO_TRADE, Posture.RISK_OFF, Posture.NEUTRAL, Posture.RISK_ON]


@dataclass(frozen=True)
class PostureLimits:
    """What a posture permits. None means 'use the configured default'."""
    allows_new_risk: bool
    max_risk_per_trade_pct: Optional[float] = None
    max_concurrent_positions: Optional[int] = None
    reason: str = ""


def limits_for(p: Posture) -> PostureLimits:
    if p is Posture.NO_TRADE:
        return PostureLimits(False, reason="posture NO_TRADE: no entries at all")
    if p is Posture.RISK_OFF:
        return PostureLimits(True, 0.01, 1,
                             reason="posture RISK_OFF: 1% per trade, one position")
    return PostureLimits(True, reason=f"posture {p.value}")


def parse(text: str) -> Posture:
    """The posture from a brief's `## Posture` section.

    Anchored on the heading rather than scanning the document: a brief
    discusses posture in prose ("a reason to downgrade posture", "no entry is
    authorised while posture is NO_TRADE" in the watchlist), and a keyword
    search would read those as the decision. Ambiguity inside the section
    resolves to the most conservative token present.
    """
    if not text:
        return Posture.NO_TRADE

    m = re.search(r"^\s*#{1,6}\s*Posture\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return Posture.NO_TRADE

    rest = text[m.end():]
    nxt = re.search(r"^\s*#{1,6}\s+\S", rest, re.MULTILINE)
    block = rest[:nxt.start()] if nxt else rest

    found = {p for p in Posture
             if re.search(rf"\b{p.value}\b", block, re.IGNORECASE)}
    if not found:
        return Posture.NO_TRADE
    for p in _SEVERITY:                      # most conservative wins
        if p in found:
            return p
    return Posture.NO_TRADE


def for_date(briefs_dir: Path, day: dt.date) -> tuple[Posture, str]:
    """Today's posture, plus a one-line note on where it came from."""
    path = Path(briefs_dir) / f"{day.isoformat()}.md"
    if not path.exists():
        return Posture.NO_TRADE, (
            f"no brief at {path} — a session that has not written today's "
            f"brief does not get to open risk")
    try:
        text = path.read_text()
    except OSError as e:
        return Posture.NO_TRADE, f"brief unreadable ({e}); failing closed"
    p = parse(text)
    return p, f"{p.value} from {path.name}"
