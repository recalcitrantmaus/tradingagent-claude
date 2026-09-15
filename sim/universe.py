"""A small, liquid universe appropriate to a $300 account.

Share price matters enormously at this size: a $580 ETF is unbuyable, so the
simulated universe is weighted toward sub-$100 instruments plus two majors
that are only reachable through options or fractional shares.
"""

UNIVERSE = {
    "BRD":  {"beta": 1.00, "idio_vol": 0.05, "px": 62.0,  "asset_class": "etf"},    # broad-market ETF proxy
    "TEC":  {"beta": 1.35, "idio_vol": 0.14, "px": 48.0,  "asset_class": "equity"},
    "FIN":  {"beta": 0.85, "idio_vol": 0.11, "px": 34.0,  "asset_class": "equity"},
    "HLTH": {"beta": 0.60, "idio_vol": 0.13, "px": 27.0,  "asset_class": "equity"},
    "ENGY": {"beta": 0.95, "idio_vol": 0.22, "px": 19.0,  "asset_class": "equity"},
    "SMCAP":{"beta": 1.25, "idio_vol": 0.28, "px": 11.0,  "asset_class": "equity"},
    "BTC":  {"beta": 1.60, "idio_vol": 0.40, "px": 95000.0, "asset_class": "crypto"},
    "ETH":  {"beta": 1.75, "idio_vol": 0.50, "px": 3200.0,  "asset_class": "crypto"},
}
