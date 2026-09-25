#!/usr/bin/env python3
"""Read-only broker check: equity, positions, open orders and protection.

Replaces the `python3 -c "from adapters.alpaca import ..."` one-liners the
Routine prompts used to carry. Those could not be covered by a permission
rule: auto mode strips `Bash(python3 -c:*)`, because it would allow any code
at all. That sent every call to the auto-mode classifier. A named module can
be allow-listed exactly (`Bash(python3 -m tools.broker_check:*)`). See
state/reviews/2026-09-25-permissions-rca.md.

Exit 1 when a position has no working stop. That is the one condition every
caller must act on, so it is signalled in the status as well as printed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def report(adapter) -> tuple[list[str], list[str]]:
    """The lines to print, and the unprotected symbols. Reads only."""
    ac = adapter.account()
    lines = [f"equity      : {ac['equity']}",
             f"cash        : {ac['cash']}"]
    positions = adapter.positions()
    lines.append(f"positions   : {positions if positions else 'none'}")
    orders = [(o.get("symbol"), o.get("side"), o.get("type"),
               o.get("time_in_force"), o.get("status"))
              for o in adapter.open_orders(nested=True)]
    lines.append(f"orders      : {orders if orders else 'none'}")
    lines.append(f"stops       : {adapter.resting_stops()}")
    unprotected = adapter.positions_without_stops()
    lines.append(f"UNPROTECTED : {unprotected}")
    return lines, unprotected


def main() -> int:
    from adapters.alpaca import AlpacaAdapter
    lines, unprotected = report(AlpacaAdapter())
    print("\n".join(lines))
    if unprotected:
        print("!! a position has no working stop: fix it or flatten it before "
              "anything else")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
