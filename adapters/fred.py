"""FRED macro series, keyless.

The jobless-claims print that set this off was unavailable because www.dol.gov
refuses us. FRED carries the same series — and the yields, spreads, CPI and VIX
the brief reasons about — as plain CSV with no key and no bot wall.

    from adapters.fred import latest
    d, v = latest("ICSA")        # initial jobless claims

Every value carries its observation date, because a macro number without the
date it describes is the kind of "fact" this project is built to refuse: stale
data presented as current is worse than no data, since it reads as sourced.

Standard library only, consistent with the rest of the adapters.
"""
from typing import List, Optional, Tuple
import datetime as dt
import urllib.error
import urllib.request

from .base import AdapterError

BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# The handful the premarket brief actually reasons about. Names are here so a
# brief cites "initial jobless claims" rather than "ICSA".
SERIES = {
    "ICSA": "initial jobless claims, weekly",
    "RSAFS": "retail sales, monthly",
    "DGS10": "10-year Treasury yield",
    "DGS2": "2-year Treasury yield",
    "T10Y2Y": "10y minus 2y spread",
    "BAMLH0A0HYM2": "high-yield credit spread",
    "CPIAUCSL": "CPI, all urban consumers",
    "UNRATE": "unemployment rate",
    "VIXCLS": "VIX close",
    "SOFR": "secured overnight financing rate",
}


def _fetch(series_id: str, timeout: int = 30) -> str:
    from tools.netcheck import user_agent
    url = f"{BASE}?id={series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise AdapterError(f"FRED {series_id} -> HTTP {e.code}") from e
    except Exception as e:
        raise AdapterError(f"FRED {series_id} unreachable: {str(e)[:110]}") from e


def series(series_id: str, limit: Optional[int] = None) -> List[Tuple[dt.date, float]]:
    """Observations, oldest first. Missing values are dropped, not guessed.

    FRED writes an unreported observation as ".". Carrying that through as 0.0
    would silently turn a gap in the data into a reading of zero, which for a
    spread or a rate is not a small error.
    """
    rows: List[Tuple[dt.date, float]] = []
    for line in _fetch(series_id).splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        raw = parts[1].strip()
        if not raw or raw == ".":
            continue
        try:
            rows.append((dt.date.fromisoformat(parts[0].strip()), float(raw)))
        except ValueError:
            continue
    if not rows:
        raise AdapterError(f"FRED {series_id} returned no usable observations")
    return rows[-limit:] if limit else rows


def latest(series_id: str) -> Tuple[dt.date, float]:
    return series(series_id)[-1]


def snapshot(ids: Optional[List[str]] = None) -> dict:
    """Current readings for the brief, each with its observation date."""
    out = {}
    for sid in (ids or list(SERIES)):
        try:
            d, v = latest(sid)
            out[sid] = {"value": v, "as_of": d.isoformat(),
                        "name": SERIES.get(sid, sid),
                        "stale_days": (dt.date.today() - d).days}
        except AdapterError as e:
            out[sid] = {"error": str(e)[:90], "name": SERIES.get(sid, sid)}
    return out
