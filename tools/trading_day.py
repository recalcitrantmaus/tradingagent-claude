#!/usr/bin/env python3
"""The mechanical spine of a Phase 2 trading day.

The skills supply judgment. This supplies the things that must happen the same
way every day regardless of what the agent thinks about the market:

    python3 -m tools.trading_day open     # preflight, reconcile, mark, halts
    python3 -m tools.trading_day preclose # cancel resting entries BEFORE the bell
    python3 -m tools.trading_day close    # reconcile, stop audit, mark, report
    python3 -m tools.trading_day week     # expectancy, costs, findings

Every subcommand reconciles against the broker first. A ledger that disagrees
with the broker is a stop-everything event: trading on a stale ledger is how a
bounded loss becomes an unbounded one.

--offline uses public market data and the stored ledger, for rehearsing the
flow before broker keys exist. It refuses to mark the day as traded.
"""
import argparse
import datetime as dt
from zoneinfo import ZoneInfo
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import DEFAULT
from engine.portfolio import Portfolio, Position
from engine.risk import RiskOfficer, State
from tools import state
from tools.review import closed_trades

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "state" / "reports"


# ----------------------------------------------------------------------
# broker access
# ----------------------------------------------------------------------
def get_broker(offline: bool):
    if offline:
        return None
    from adapters.alpaca import AlpacaAdapter
    return AlpacaAdapter(live=False)


# Detection is tight; response is proportionate. An unexplained cent and an
# unexplained dollar have the same causes — an unrecorded fill, a fee, a
# position opened and closed between two firings, a bug in the submit path —
# so both are reported. Only the larger one stops the day.
DRIFT_NOTE = 0.005
DRIFT_HALT_ABS = 1.00
DRIFT_HALT_PCT = 0.005



# ----------------------------------------------------------------------
# What "today" means (T-9)
# ----------------------------------------------------------------------
# The trading day is an EXCHANGE concept and the exchange is in New York.
# Everything here used to key on `dt.date.today()` — the container's local
# date, which is UTC — against timestamps stored in UTC. Two things were
# wrong with that:
#
#   1. UTC midnight is 20:00 ET, i.e. four hours AFTER the close but on the
#      same session's evening. So "today's" drift window opened the previous
#      evening. On 2026-09-22 the close session's four readings included one
#      from Monday 22:32 ET.
#   2. `date.today()` is the MACHINE's date. The same code on an ET host
#      would compare an ET date against UTC timestamp strings and bucket
#      differently — or match nothing at all. A check decided by where it
#      runs, which is the pattern this repo keeps finding (M-28).
#
# Harmless while drift is +0.0000. Not harmless afterwards: the cumulative
# figure feeds `drift_halts`, so an evening's drift would count against the
# wrong session — and crypto, which the plan permits, fills around the clock.
#
# ZoneInfo("America/New_York") rather than a fixed -05:00: it carries DST, so
# this stays correct across the November and March transitions without anyone
# remembering to change it.
ET = ZoneInfo("America/New_York")


def trading_date(when: Optional[dt.datetime] = None) -> dt.date:
    """The exchange's calendar date for an instant (default: now)."""
    when = when or dt.datetime.now(dt.timezone.utc)
    if when.tzinfo is None:                 # stored naive == stored UTC
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(ET).date()


def _parse_ts(raw) -> Optional[dt.datetime]:
    """Parse a recorded timestamp, or None. A row whose timestamp cannot be
    read is EXCLUDED rather than silently bucketed into today — a drift
    reading attributed to the wrong session is worse than one that is missing,
    because the halt check believes it."""
    try:
        return dt.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def drift_today(ledger: Dict, today: Optional[dt.date] = None) -> Tuple[float, int]:
    """Drift already recorded today, and how many readings produced it.

    Each reconciliation reports the displacement since the LAST anchor, then
    re-anchors — so a day's readings are increments, not repeats, and summing
    them gives total displacement from the day's first observation.

    That matters because `trading_day open` runs at every management firing.
    Three separate 40-cent surprises are each below the halt threshold and
    each correctly reported, while $1.20 of the account has gone somewhere
    nobody can explain. Reporting only the last one understates the day.
    """
    day = today or trading_date()
    rows = []
    for r in (ledger.get("reconcile_drift") or []):
        ts = _parse_ts(r.get("at"))
        if ts is not None and trading_date(ts) == day:
            rows.append(r)
    return sum(r.get("drift", 0.0) for r in rows), len(rows)


def cash_effect(f: Dict) -> float:
    """What a recorded fill did to cash. Buys consume it, sells return it."""
    gross = f.get("qty", 0.0) * f.get("price", 0.0) * f.get("multiplier", 1)
    fees = f.get("fees", 0.0) or 0.0
    return -(gross + fees) if f.get("side") == "buy" else (gross - fees)


def expected_cash(ledger: Dict, fills: List[Dict]) -> Tuple[Optional[float], int]:
    """Broker cash we should see, from the last anchor plus fills since it.

    Returns (expected, n_fills_counted), or (None, 0) when no anchor exists —
    the first run after this check was added, which is not a failure.
    """
    anchor = ledger.get("broker_cash")
    if anchor is None:
        return None, 0
    since = ledger.get("broker_cash_at") or ""
    counted = [f for f in fills
               if not f.get("dry_run") and str(f.get("ts", "")) > since]
    return anchor + sum(cash_effect(f) for f in counted), len(counted)
def post_broker_fills(broker, ledger: Dict) -> List[str]:
    """Record every fill the BROKER reports that our log has not got.

    Phase 2's first real fill was recorded nowhere, and the reason is a gap
    between two correct-looking pieces of code:

      - `paper_session --submit` waits FILL_WAIT_SECONDS (30s) for the entry
        it just sent, records it if it fills, and otherwise files it under
        `ledger["working_orders"]` with the comment "session-close must
        reconcile". DT filled 5m35s after submission — a limit order resting
        for minutes is the NORMAL case, not an edge case.
      - Nothing ever reconciled `working_orders`. It is written by
        `paper_session` and cleared by `preclose`, and swept by no one. The
        promise in that comment was never implemented.

    And even a working sweep of `working_orders` would only catch ENTRIES.
    Nothing submits a stop or a take-profit — they are OCO legs that fire on
    their own — so no exit has ever had a code path that records it. Neither
    did the manual flatten on 2026-09-23.

    So this does not sweep our list of orders. It asks the broker what filled
    and writes down anything missing, which is the only version that cannot be
    outflanked by a fill we did not originate. Deduped on Alpaca's activity id.

    Consequence if it does not run, measured live: the ledger's expected cash
    stays at the pre-trade anchor while the broker's moves by the trade, so
    `reconcile` reports a $58.47 "unexplained drift" against a ~$1.50 halt
    threshold and stops the day — a halt that is arithmetically correct and
    describes a bookkeeping hole rather than a missing dollar.
    """
    if not hasattr(broker, "fills_since"):
        return []
    known = {f.get("activity_id") for f in state.read_fills()
             if f.get("activity_id")}
    since = (ledger.get("broker_cash_at") or "")[:10] or \
        (trading_date() - dt.timedelta(days=5)).isoformat()
    try:
        rows = broker.fills_since(since)
    except Exception as e:                       # never block a session on this
        return [f"could not read the broker fill feed: {str(e)[:120]}"]

    notes = []
    for r in rows:
        if r.get("activity_id") in known:
            continue
        row = {
            "symbol": r["symbol"], "side": r["side"], "qty": r["qty"],
            "price": r["price"], "fees": 0.0, "multiplier": 1,
            "reason": "entry" if r["side"] == "buy" else "exit",
            "activity_id": r.get("activity_id"), "order_id": r.get("order_id"),
            "ts": r.get("at"), "dry_run": False,
            "source": "broker reconciliation",
            "thesis": "recovered from the broker fill feed, not from submission",
        }
        # An entry without its stop cannot produce an R, and a trade with no R
        # never reaches the expectancy table — so "positive expectancy" would
        # stay unmeasurable forever while trades accumulated. Take the stop
        # from the broker's own bracket leg: that is the stop that was actually
        # resting, not the one the plan asked for.
        if r["side"] == "buy" and r.get("order_id") and hasattr(broker, "stop_of_order"):
            st = broker.stop_of_order(r["order_id"])
            if st:
                row["stop"] = st
            else:
                notes.append(f"  ! {r['symbol']} entry recovered with NO stop "
                             f"price — its R will be unmeasurable")
        state.append_fill(row)
        notes.append(f"POSTED {r['side'].upper()} {r['qty']:g} {r['symbol']} "
                     f"@ {r['price']:.4f} from the broker feed "
                     f"({r.get('at', '')[11:19]}Z) — not recorded at submission")
    return notes




def reconcile(broker, ledger: Dict) -> Tuple[bool, List[str], Dict]:
    """Compare the broker's truth against ours. Returns (ok, notes, snapshot)."""
    notes: List[str] = []
    if broker is None:
        curve = ledger.get("equity_curve") or []
        eq = curve[-1][1] if curve else ledger.get("cash", DEFAULT.starting_equity)
        # Do not present a stored number as current. ledger["cash"] was write-
        # once dead data until 2026-09-20 and would have read $300.00 forever;
        # say what was last OBSERVED and when, so a stale figure looks stale.
        seen = ledger.get("broker_cash")
        when = ledger.get("broker_cash_at") or "never"
        notes.append(
            "OFFLINE: using the stored ledger, not the broker. Last broker "
            f"cash observed: {('$%.2f' % seen) if seen is not None else 'never'} "
            f"at {when}")
        return True, notes, {
            "equity": eq, "cash": seen if seen is not None else ledger.get("cash"),
            "positions": [], "unprotected": [],
            "daytrades": len(ledger.get("day_trades", []))}

    acct = broker.account()
    positions = broker.positions()
    unprotected = broker.positions_without_stops()

    if acct["trading_blocked"]:
        notes.append("BROKER REPORTS trading_blocked — stop")

    # Post anything the broker filled that our log has not got, BEFORE the
    # drift check reads it — otherwise the drift check measures our own
    # bookkeeping hole and halts the day over it.
    for n in post_broker_fills(broker, ledger):
        notes.append(n)

    # --- cash drift ---------------------------------------------------
    # Equity moves every second for legitimate reasons, so comparing it needs
    # a tolerance wide enough to catch nothing. Cash only moves when something
    # HAPPENED. That makes it the invariant worth checking, and it is the one
    # that caught nothing on 2026-09-18 when $300.00 became $299.99 with every
    # control reporting clean.
    drift = None
    exp, n_fills = expected_cash(ledger, state.read_fills())
    if exp is None:
        notes.append("no cash anchor yet; recording one (first run of this check)")
    else:
        drift = acct["cash"] - exp
        if abs(drift) > DRIFT_NOTE:
            notes.append(
                f"CASH DRIFT {drift:+.4f}: broker ${acct['cash']:.2f} vs "
                f"${exp:.2f} expected (anchor ${ledger.get('broker_cash'):.2f} "
                f"+ {n_fills} recorded fill(s) since "
                f"{ledger.get('broker_cash_at')}). Unexplained by the fill log.")

    # Each reading is an increment since the last anchor, so the day's total
    # is their sum. Without this, three sub-threshold surprises read as three
    # small notes instead of one material one.
    prior, n_prior = drift_today(ledger)
    cum = (drift or 0.0) + prior
    if n_prior and abs(cum) > DRIFT_NOTE:
        notes.append(
            f"CUMULATIVE DRIFT TODAY {cum:+.4f} across {n_prior + 1} "
            f"reconciliation(s). Individually small, collectively this is how "
            f"much of the account has moved with no recorded cause.")
    ledger_syms = set(ledger.get("positions", {}))
    broker_syms = {p["symbol"] for p in positions}
    if ledger_syms != broker_syms:
        only_ledger = ledger_syms - broker_syms
        only_broker = broker_syms - ledger_syms
        if only_ledger:
            notes.append(f"in ledger but NOT at broker: {sorted(only_ledger)}")
        if only_broker:
            notes.append(f"at broker but NOT in ledger: {sorted(only_broker)}")
    if unprotected:
        notes.append(f"positions with NO resting stop: {unprotected}")

    halt_at = max(DRIFT_HALT_ABS, DRIFT_HALT_PCT * (acct["equity"] or 0.0))
    single_halts = drift is not None and abs(drift) > halt_at
    cum_halts = bool(n_prior) and abs(cum) > halt_at
    drift_halts = single_halts or cum_halts
    if drift_halts:
        which = (f"drift {abs(drift):.2f}" if single_halts
                 else f"cumulative drift {abs(cum):.2f} across the day")
        notes.append(f"{which} exceeds {halt_at:.2f} — "
                     "the ledger and the broker disagree materially. "
                     "DO NOT TRADE until this is explained.")

    ok = (not acct["trading_blocked"] and ledger_syms == broker_syms
          and not drift_halts)
    return ok, notes, {"equity": acct["equity"], "cash": acct["cash"],
                       "positions": positions, "unprotected": unprotected,
                       "daytrades": acct["daytrade_count"],
                       "cash_drift": drift,
                       "cash_drift_today": cum if n_prior else drift,
                       "drift_readings_today": n_prior + 1}



def anchor_cash(ledger: Dict, snap: Dict, when: str = "") -> None:
    """Re-anchor the cash invariant to what the broker just said.

    Called at BOTH open and close. Without this the check has no baseline on
    the next run, which is exactly how ledger["cash"] came to sit at its
    initial 300.0 while the broker moved: written once at birth and never
    again.
    """
    if snap.get("cash") is None:
        return
    ledger["broker_cash"] = snap["cash"]
    ledger["broker_equity"] = snap.get("equity")
    ledger["broker_cash_at"] = when or dt.datetime.now(dt.timezone.utc).isoformat()
    ledger["cash"] = snap["cash"]          # keep the legacy field honest too
    if snap.get("cash_drift") is not None:
        hist = ledger.setdefault("reconcile_drift", [])
        hist.append({"at": ledger["broker_cash_at"],
                     "drift": round(snap["cash_drift"], 4),
                     "broker_cash": snap["cash"]})
        del hist[:-60]                      # keep it bounded; 60 marks is ample


def build_engine(snapshot: Dict, ledger: Dict, today: dt.date
                 ) -> Tuple[Portfolio, RiskOfficer]:
    pf = Portfolio(ledger.get("starting_equity", DEFAULT.starting_equity))
    pf.cash = snapshot["cash"]
    pf.peak_equity = max(ledger.get("peak_equity", snapshot["equity"]),
                         snapshot["equity"])
    for p in snapshot["positions"]:
        pf.positions[p["symbol"]] = Position(
            symbol=p["symbol"], asset_class="equity", qty=p["qty"],
            avg_price=p["avg_price"], opened_at=today)

    ro = RiskOfficer(DEFAULT)
    ro.day_start_equity = ledger.get("day_start_equity", snapshot["equity"])
    ro.week_start_equity = ledger.get("week_start_equity", snapshot["equity"])
    try:
        ro.state = State(ledger.get("risk_state", "NORMAL"))
    except ValueError:
        ro.state = State.NORMAL

    rs = [t["R"] for t in closed_trades(state.read_fills()) if t["R"] is not None]
    ro.set_track_record(len(rs), statistics.mean(rs) if rs else 0.0)
    return pf, ro


def prices_of(snapshot: Dict) -> Dict[str, float]:
    return {p["symbol"]: (p["market_value"] / p["qty"]) if p["qty"] else 0.0
            for p in snapshot["positions"]}


# ----------------------------------------------------------------------
# subcommands
# ----------------------------------------------------------------------
def cmd_open(args) -> int:
    today = trading_date()
    ledger = state.load()
    broker = get_broker(args.offline)
    ok, notes, snap = reconcile(broker, ledger)

    print(f"=== OPEN {today} ===")
    print(f"equity        ${snap['equity']:,.2f}   cash ${snap['cash']:,.2f}")
    for n in notes:
        print(f"  ! {n}")
    if not ok:
        print("\nRECONCILIATION FAILED — do not trade. Resolve the discrepancy "
              "above, by hand if necessary, before any order.")
        return 1

    pf, ro = build_engine(snap, ledger, today)
    prices = prices_of(snap)

    # A new week resets the weekly anchor; a new day resets the daily one.
    #
    # These must fire ONCE PER DAY and ONCE PER WEEK, not once per invocation.
    # The line below used to read `ledger["day_start_equity"] = snap["equity"]`
    # unconditionally, and `trading_day open` runs at every management firing
    # — midday and pre-close as well as the open. So a day that was -3% by
    # noon re-anchored at noon, and a further -3% read as -3%: the -4% daily
    # halt measured from a baseline that walked downhill with the losses and
    # could not fire. The weekly anchor was worse, because `weekday() == 0`
    # made Monday re-anchor on EVERY run, and a holiday Monday meant the week
    # never re-anchored at all.
    #
    # Anchors are therefore keyed to the calendar, not to the call.
    week_key = "%d-W%02d" % today.isocalendar()[:2]
    if ledger.get("week_start_key") != week_key or not ledger.get("week_start_equity"):
        ledger["week_start_equity"] = snap["equity"]
        ledger["week_start_key"] = week_key
    ro.week_start_equity = ledger["week_start_equity"]

    ro.start_day(today, snap["equity"])
    if ledger.get("day_start_key") != today.isoformat():
        ledger["day_start_equity"] = snap["equity"]
        ledger["day_start_key"] = today.isoformat()
    # start_day() seeded the officer from today's equity; re-point it at the
    # real anchor so the breaker measures the whole day, not this firing.
    ro.day_start_equity = ledger["day_start_equity"]

    st = ro.update(today, pf, prices)
    wk = (snap["equity"] / ledger["week_start_equity"] - 1) if ledger["week_start_equity"] else 0.0

    print(f"week-to-date  {wk:+.2%}   drawdown {pf.drawdown(prices):.2%} "
          f"(lock at {DEFAULT.max_drawdown_lock_pct:.0%})")
    print(f"risk state    {st.value}")
    print(f"track record  {ro.closed_trades} closed trades, "
          f"expectancy {ro.expectancy_R:+.3f}R")
    print(f"day trades    {snap['daytrades']} / {DEFAULT.max_day_trades_per_5d}")
    print(f"options       {'unlocked' if ro.closed_trades >= DEFAULT.option_min_closed_trades and ro.expectancy_R >= DEFAULT.option_min_expectancy_R and snap['equity'] >= DEFAULT.option_min_equity else 'LOCKED'}")
    if snap["positions"]:
        print("\nopen positions:")
        for p in snap["positions"]:
            flag = "  !! NO STOP" if p["symbol"] in snap["unprotected"] else ""
            print(f"  {p['symbol']:8} qty {p['qty']:>8g} @ {p['avg_price']:>9.2f} "
                  f"P&L {p['unrealized_pl']:>+8.2f}{flag}")

    ledger["risk_state"] = st.value
    ledger["peak_equity"] = pf.peak_equity
    ledger["last_reconciled"] = today.isoformat()
    ledger["positions"] = {p["symbol"]: p for p in snap["positions"]}
    anchor_cash(ledger, snap)
    if ro.journal:
        ledger.setdefault("halts", []).extend(
            [{"date": today.isoformat(), "event": j} for j in ro.journal])
    if not args.offline:
        state.save(ledger)

    if st != State.NORMAL:
        print(f"\n*** {st.value}: no new risk. Manage open positions only.")
        if st == State.LOCKED:
            print("*** LOCKED requires a human. Do not trade. Escalate today.")
        return 1
    print("\nNORMAL. Proceed to the premarket-brief skill.")
    return 0


def cmd_close(args) -> int:
    today = trading_date()
    ledger = state.load()
    broker = get_broker(args.offline)
    ok, notes, snap = reconcile(broker, ledger)

    pf, ro = build_engine(snap, ledger, today)
    prices = prices_of(snap)
    eq = snap["equity"]
    day_start = ledger.get("day_start_equity", eq)
    week_start = ledger.get("week_start_equity", eq)
    start = ledger.get("starting_equity", DEFAULT.starting_equity)

    day_pnl = eq / day_start - 1 if day_start else 0.0
    wk_pnl = eq / week_start - 1 if week_start else 0.0
    st = ro.update(today, pf, prices)

    # Overnight risk: stops do not hold through gaps, so price the 2x case.
    risk_1x = risk_2x = 0.0
    for p in snap["positions"]:
        pos = pf.positions[p["symbol"]]
        stop = ledger.get("positions", {}).get(p["symbol"], {}).get("stop")
        px = prices.get(p["symbol"], pos.avg_price)
        if stop:
            risk_1x += (px - stop) * pos.qty
            risk_2x += (px - stop) * 2 * pos.qty
        else:
            risk_1x += px * pos.qty * 0.10     # no stop: assume a bad 10% night
            risk_2x += px * pos.qty * 0.20

    lines = [
        f"# Session report — {today}",
        "",
        f"Equity: ${eq:,.2f} (day {day_pnl:+.2%}, week {wk_pnl:+.2%}, "
        f"since inception {eq / start - 1:+.2%})",
        f"Risk state: {st.value}",
        f"Drawdown from peak: {pf.drawdown(prices):.2%}",
        f"Track record: {ro.closed_trades} closed trades, "
        f"expectancy {ro.expectancy_R:+.3f}R",
        "",
        "## Overnight risk",
        f"If every stop fills at its level: -${risk_1x:,.2f} "
        f"({risk_1x / eq:.2%} of equity)" if eq else "n/a",
        f"If they all gap 2x through: -${risk_2x:,.2f} "
        f"({risk_2x / eq:.2%} of equity)" if eq else "n/a",
    ]
    if eq and risk_2x / eq > DEFAULT.weekly_loss_halt_pct:
        lines.append(f"**2x-gap loss exceeds the {DEFAULT.weekly_loss_halt_pct:.0%} "
                     "weekly halt — reduce overnight exposure now.**")

    # Entries are GTC so a filled position's stop survives the close (see
    # OrderTicket.time_in_force). The corollary is that an unfilled entry would
    # survive too and fire tomorrow on a gap against a stale thesis, so it is
    # cancelled here. Protective legs are deliberately left resting.
    cancelled = []
    if broker is not None:
        try:
            cancelled = broker.cancel_unfilled_entries()
        except Exception as e:                # never let cleanup kill the report
            notes.append(f"could not cancel resting entries: {str(e)[:120]}")
        if cancelled:
            notes.append(f"cancelled resting entry orders: {cancelled}")
        # Re-check AFTER cancelling: if that call stripped a stop by mistake,
        # the report must say so tonight, not discover it tomorrow.
        try:
            still = broker.positions_without_stops()
            if still != snap["unprotected"]:
                snap["unprotected"] = still
                notes.append(f"unprotected AFTER cancelling entries: {still}")
        except Exception as e:
            notes.append(f"could not re-verify stops: {str(e)[:120]}")

    lines += ["", "## Open overnight"]
    if snap["positions"]:
        for p in snap["positions"]:
            flag = "  **NO STOP — flatten or fix**" if p["symbol"] in snap["unprotected"] else ""
            lines.append(f"- {p['symbol']} qty {p['qty']:g} @ {p['avg_price']:.2f}, "
                         f"P&L {p['unrealized_pl']:+.2f}{flag}")
    else:
        lines.append("- none (flat)")

    # State the cash figure unconditionally, including when it is zero. A
    # report that mentions drift only when there is some teaches the reader
    # that silence means "not checked" — which is exactly how a $300.00 that
    # should have read $299.99 went unremarked for a day.
    cum = snap.get("cash_drift_today")
    reads = snap.get("drift_readings_today") or 0
    lines += ["", "## Cash reconciliation"]
    if cum is None:
        lines.append("- no anchor yet; one was recorded today")
    else:
        lines.append(
            f"- unexplained cash drift today: **${cum:+.4f}** across {reads} "
            f"reconciliation(s)" + ("  — clean" if abs(cum) <= DRIFT_NOTE else
            "  — **unexplained by the fill log**"))

    if notes:
        lines += ["", "## Reconciliation notes"] + [f"- {n}" for n in notes]

    lines += ["", "## Escalate to the human today?"]
    escalations = []
    if st == State.LOCKED:
        escalations.append("risk state is LOCKED — only a human can clear it")
    if not ok:
        escalations.append("the ledger did not reconcile")
    if snap["unprotected"]:
        escalations.append(f"unprotected positions: {snap['unprotected']}")
    if wk_pnl <= -DEFAULT.weekly_loss_halt_pct:
        escalations.append(f"weekly loss {wk_pnl:.2%}")
    if ro.closed_trades >= 20 and ro.expectancy_R <= 0:
        escalations.append(f"expectancy {ro.expectancy_R:+.3f}R over "
                           f"{ro.closed_trades} trades is not positive")
    lines += [f"- {e}" for e in escalations] or ["- nothing"]

    report = "\n".join(lines)
    print(report)

    if not args.offline:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{today.isoformat()}.md").write_text(report + "\n")
        curve = ledger.setdefault("equity_curve", [])
        curve.append([today.isoformat(), eq])
        ledger["peak_equity"] = max(ledger.get("peak_equity", eq), eq)
        ledger["risk_state"] = st.value
        ledger["last_reconciled"] = today.isoformat()
        anchor_cash(ledger, snap)
        ledger.setdefault("days", []).append(
            {"date": today.isoformat(), "equity": eq, "day_pnl": round(day_pnl, 5),
             "risk_state": st.value, "escalations": escalations})
        state.save(ledger)
        print(f"\nwrote state/reports/{today.isoformat()}.md")

    return 1 if escalations else 0



def cmd_preclose(args) -> int:
    """Close the entry book BEFORE the bell, not after it.

    `cancel_unfilled_entries()` lived only in `close`, which runs after 16:00.
    That is correctly scoped and wrongly timed, and the pre-close session on
    2026-09-21 found why: the closing cross is the largest print of the day
    and the event most likely to fill a resting limit, so an entry cancelled
    after the bell was live through the auction that would have filled it.

    The overnight case is worse. A GTC buy limit **gaps through its own
    protection**: an open below the limit fills at the open price, which can
    be under the stop, so the bracket does not bound the loss the way it does
    on an intraday fill.

    So the cancellation moves here, into the management window, and `close`
    keeps it as a backstop for the day this session does not run.
    """
    today = trading_date()
    ledger = state.load()
    broker = get_broker(args.offline)
    ok, notes, snap = reconcile(broker, ledger)

    print(f"=== PRE-CLOSE {today} ===")
    print(f"equity        ${snap['equity']:,.2f}   cash ${snap['cash']:,.2f}")
    for n in notes:
        print(f"  ! {n}")
    if not ok:
        print("\nRECONCILIATION FAILED — resolve before the bell.")
        return 1

    cancelled: List[str] = []
    if broker is not None:
        try:
            cancelled = broker.cancel_unfilled_entries()
        except Exception as e:
            print(f"  !! could not cancel resting entries: {str(e)[:120]}")
            return 1
        print(f"cancelled entries: {cancelled or 'none resting'}")

        # Re-read AFTER cancelling. If that call took a protective leg off an
        # open position, the time to find out is now, with the market open and
        # something still doable about it.
        try:
            still = broker.positions_without_stops()
        except Exception as e:
            print(f"  !! could not re-verify stops: {str(e)[:120]}")
            return 1
        if still:
            print(f"  !! UNPROTECTED AFTER CANCELLING: {still}")
            print("     Fix or flatten before the bell. Do not carry this.")
            return 1
        print("protection    : every position has a live stop")

    anchor_cash(ledger, snap)
    ledger["working_orders"] = []
    state.save(ledger)
    print(f"\n{len(snap['positions'])} position(s) carried overnight.")
    return 0


def cmd_week(args) -> int:
    ledger = state.load()
    trades = closed_trades(state.read_fills())
    days = ledger.get("days", [])[-5:]
    start = ledger.get("week_start_equity") or ledger.get("starting_equity", 300.0)
    eq = days[-1]["equity"] if days else start

    rs = [t["R"] for t in trades if t["R"] is not None]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    costs = sum(t["fees"] for t in trades)
    net = sum(t["pnl"] for t in trades)

    print("=== WEEK REVIEW ===")
    print(f"equity          ${eq:,.2f}  (week {eq / start - 1:+.2%})")
    print(f"target gap      {eq / start - 1:+.2%} vs +5.00% "
          f"-> {(eq / start - 1) - 0.05:+.2%}")
    print(f"sessions        {len(days)}")
    print(f"closed trades   {len(trades)} ({len(wins)}W / {len(losses)}L)")
    if trades:
        print(f"win rate        {len(wins) / len(trades):.1%}")
        print(f"net P&L         ${net:,.2f}")
        print(f"costs           ${costs:,.2f}"
              f"{'   <-- COSTS EXCEED GAINS: trading too often' if costs > max(net, 0) else ''}")
    if rs:
        e = statistics.mean(rs)
        print(f"expectancy      {e:+.3f}R over {len(rs)} trades"
              f"{'   <-- NEGATIVE EDGE' if e <= 0 else ''}")
    else:
        print("expectancy      not measurable yet (no closed trades with a stop)")

    # --- Phase 2 exit criteria (T-8) -----------------------------------
    #
    # Three states, not two. "zero guardrail breaches", "costs below gains"
    # and "never LOCKED" all passed VACUOUSLY on an account that had never
    # traded — `all()` over an empty list is True, and "costs below gains"
    # carried an explicit `if trades else True`. Each is a defensible vacuous
    # truth on its own. Together they made a flat account print three [ok]s
    # and read THREE-FIFTHS OF THE WAY TO PHASE 2 EXIT, which is the kind of
    # figure that gets repeated in a summary without its denominator.
    #
    # It is the same shape as "no protective leg was stripped — vacuously,
    # with no position": a check that cannot fail is not evidence, and a
    # scorecard that cannot tell "passed" from "never ran" rewards inactivity.
    # Doing nothing is now visibly unscored rather than quietly winning.
    #
    # A criterion is MEASURABLE only if the thing it judges exists. Its
    # `measurable` flag says so, and the exit gate requires every criterion to
    # be both measurable and passed.
    # Measurability keys on TRADES, not on sessions observed. Tying it to
    # sessions was the first attempt and it was too weak: it still printed
    # two [ok]s for a flat account, because "zero guardrail breaches" and
    # "never LOCKED" pass trivially when nothing has been risked. You cannot
    # breach a rail you never touched, and LOCKED requires a -20% drawdown,
    # which requires losses, which requires trades. A guardrail that was
    # never exercised was not honoured — it was untested.
    #
    # So every criterion except the trade COUNT is unmeasurable until the
    # account trades, and a flat account reads 0/5. That is the whole point:
    # inactivity should score nothing, not most of the way to exit.
    has_trades = bool(trades)
    has_days = has_trades
    print("\n--- Phase 2 exit criteria ---")
    crit = [
        ("30+ closed trades", len(trades) >= 30, True, f"{len(trades)}/30"),
        ("positive expectancy", bool(rs) and statistics.mean(rs) > 0, bool(rs),
         f"{statistics.mean(rs):+.3f}R" if rs else "no closed trade with a stop"),
        ("zero guardrail breaches",
         not any(d.get("escalations") for d in ledger.get("days", [])),
         has_days,
         f"{sum(len(d.get('escalations', [])) for d in ledger.get('days', []))} "
         f"escalations over {len(ledger.get('days', []))} session(s)"),
        ("costs below gains", has_trades and costs <= max(net, 0), has_trades,
         f"${costs:,.2f} vs ${net:,.2f}" if has_trades else "no trade has cost anything yet"),
        ("never LOCKED", all(d.get("risk_state") != "LOCKED"
                             for d in ledger.get("days", [])), has_days,
         f"{len(ledger.get('days', []))} session(s) observed"),
    ]
    for name, passed, measurable, detail in crit:
        mark = "ok" if (measurable and passed) else ("XX" if measurable else "--")
        print(f"  [{mark}] {name:26} {detail}")
    n_pass = sum(1 for _, ps, m, _ in crit if m and ps)
    n_unmeasurable = sum(1 for _, _, m, _ in crit if not m)
    print(f"\n  {n_pass}/{len(crit)} met"
          + (f", {n_unmeasurable} NOT YET MEASURABLE — an account that has not "
             f"traded cannot pass these" if n_unmeasurable else ""))
    print("\nNote: hitting +5% in a week is NOT an exit criterion. "
          "Report the gap; never close it with leverage.")
    return 0 if all(m and ps for _, ps, m, _ in crit) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command",
                    choices=["open", "preclose", "close", "week"])
    ap.add_argument("--offline", action="store_true",
                    help="rehearse without a broker; does not persist state")
    a = ap.parse_args()
    return {"open": cmd_open, "preclose": cmd_preclose,
            "close": cmd_close, "week": cmd_week}[a.command](a)


if __name__ == "__main__":
    raise SystemExit(main())
