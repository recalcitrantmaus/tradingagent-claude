#!/usr/bin/env python3
"""Prove the order path works, without taking a position.

The submit path had never executed after two sessions — every day ended with
an empty plan, so `AlpacaAdapter.submit` was untested against a real broker.
That is a mechanical risk independent of any strategy: if the bracket shape is
wrong, the first real trade discovers it, unattended, with money on it.

This places one bracket order priced far enough below the market that it
cannot fill, checks that Alpaca accepted it AND attached the protective legs,
then cancels it. It is not a trade and is never recorded as one: nothing is
written to state/fills.jsonl or the ledger, so measured expectancy and the
option-unlock gate cannot see it.

    python3 -m tools.smoke_submit --symbol F

Refuses to run unless the market is open and the account is flat, so a test
order can never be confused with, or interfere with, real positions.
"""
import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.alpaca import AlpacaAdapter, DATA
from adapters.base import AdapterError, OrderTicket

UNFILLABLE_DISCOUNT = 0.85      # limit at 85% of last -> ~15% below the market


def last_price(a: AlpacaAdapter, symbol: str) -> float:
    s = a._request("GET", f"{DATA}/v2/stocks/snapshots?symbols={symbol}")
    d = s.get(symbol) or {}
    px = (d.get("latestTrade") or {}).get("p") or (d.get("dailyBar") or {}).get("c")
    if not px:
        raise SystemExit(f"no price for {symbol}")
    return float(px)


def check(a: AlpacaAdapter) -> None:
    if not a.clock().get("is_open"):
        raise SystemExit("market is closed — a resting test order would sit "
                         "overnight. Refusing.")
    if a.positions():
        raise SystemExit("account is not flat. Refusing: a test order must "
                         "never be confusable with a real position.")
    if a.open_orders():
        raise SystemExit("there are already open orders. Refusing.")


def attempt(a: AlpacaAdapter, ticket: OrderTicket, label: str) -> dict:
    print(f"\n--- {label} ---")
    print(f"  {ticket.human()}")
    try:
        r = a.submit(ticket)
    except AdapterError as e:
        print(f"  REJECTED by Alpaca: {str(e)[:220]}")
        return {"accepted": False, "error": str(e)}
    oid = r.get("id")
    print(f"  ACCEPTED id={oid} status={r.get('status')} class={r.get('order_class')}")
    legs = r.get("legs") or []
    kinds = [(l.get("type"), l.get("stop_price") or l.get("limit_price")) for l in legs]
    print(f"  legs attached: {len(legs)} -> {kinds}")
    if not legs:
        print("  !! NO PROTECTIVE LEGS. An entry without an attached stop is "
              "the state this system exists to prevent.")
    return {"accepted": True, "id": oid, "legs": len(legs), "raw_status": r.get("status")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="F")
    a_ = ap.parse_args()

    a = AlpacaAdapter(live=False)
    check(a)

    px = last_price(a, a_.symbol)
    limit = round(px * UNFILLABLE_DISCOUNT, 2)
    stop = round(limit * 0.94, 2)
    target = round(limit * 1.20, 2)
    print(f"{a_.symbol}: last {px:.2f} -> unfillable limit {limit:.2f} "
          f"({(limit/px - 1) * 100:.1f}% below), stop {stop:.2f}, target {target:.2f}")

    results = {}
    try:
        results["whole"] = attempt(a, OrderTicket(
            symbol=a_.symbol, asset_class="equity", side="buy", qty=1,
            limit_price=limit, stop_price=stop, take_profit=target,
            thesis="SMOKE TEST — not a trade, must not fill"), "whole share, bracket")

        # Does a fractional quantity survive a bracket? This decides whether the
        # ~$75 affordability ceiling can ever move: fractional sizing would open
        # the whole market to a $300 account, but only if the stop can still be
        # attached atomically. An entry that cannot carry its stop is not worth
        # the wider universe.
        #
        # TWO probes, because one stopped being enough. On 2026-09-17 a
        # fractional bracket was rejected with "fractional orders must be
        # simple orders" — the order_class was the problem, which is what
        # D-17 rests on. After brackets became GTC on 2026-09-18 the SAME
        # probe came back "fractional orders must be DAY orders": the broker
        # now rejects on time_in_force first and never reaches the class
        # check. The test kept printing the same conclusion from evidence
        # that no longer supported it. So probe the TIF constraint and the
        # order-class constraint separately.
        results["fractional_gtc"] = attempt(a, OrderTicket(
            symbol=a_.symbol, asset_class="equity", side="buy", qty=0.5,
            limit_price=limit, stop_price=stop, take_profit=target,
            thesis="SMOKE TEST — fractional + gtc probe"),
            "fractional 0.5, bracket, gtc (expect: TIF rejection)")

        results["fractional"] = attempt(a, OrderTicket(
            symbol=a_.symbol, asset_class="equity", side="buy", qty=0.5,
            limit_price=limit, stop_price=stop, take_profit=target,
            time_in_force="day",
            thesis="SMOKE TEST — fractional bracket probe"),
            "fractional 0.5, bracket, day (expect: order_class rejection)")
    finally:
        print("\n--- cleanup ---")
        try:
            a.cancel_all()
            time.sleep(2)
        except AdapterError as e:
            print(f"  cancel_all failed: {str(e)[:150]}")
        oo, pos = a.open_orders(), a.positions()
        print(f"  open orders after cancel: {oo or 'none'}")
        print(f"  positions after cancel  : {pos or 'none'}")
        if oo or pos:
            print("  !! NOT CLEAN — resolve by hand before trading.")
        else:
            print("  clean. Nothing left resting, no position taken.")

    print("\n--- verdict ---")
    w, f = results.get("whole", {}), results.get("fractional", {})
    g = results.get("fractional_gtc", {})
    legs_note = f", {w.get('legs')} legs" if w.get("accepted") else ""
    verdict_w = "ACCEPTED" if w.get("accepted") else "REJECTED"
    print(f"  whole-share bracket : {verdict_w}{legs_note}")
    print(f"  fractional + gtc    : {'ACCEPTED' if g.get('accepted') else 'REJECTED'}"
          f"   (tests time_in_force)")
    print(f"  fractional + day    : {'ACCEPTED' if f.get('accepted') else 'REJECTED'}"
          f"   (tests order_class — this is the one D-17 rests on)")
    if w.get("accepted") and w.get("legs", 0) >= 1:
        print("  The submit path works and the stop attaches atomically.")
    if not f.get("accepted"):
        print("  Fractional cannot carry a bracket -> the ~$75 ceiling stands,")
        print("  and widening the universe by dropping whole-share sizing would")
        print("  mean giving up the atomic stop. Not a trade worth making.")
    else:
        print("  !! A FRACTIONAL DAY BRACKET WAS ACCEPTED. D-17 assumed this")
        print("     was impossible and the $75 single-position ceiling was")
        print("     argued from it. Re-open that decision before trusting it.")
    print("\n  Nothing was recorded: state/fills.jsonl and the ledger untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
