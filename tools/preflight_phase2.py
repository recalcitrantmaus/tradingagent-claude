#!/usr/bin/env python3
"""One command: is this session ready to run Phase 2?

Run it first in any new session. It checks everything that has to be true
before paper trading means anything, and says exactly what to fix.

    python3 -m tools.preflight_phase2
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []


def check(name: str, fix: str = ""):
    def deco(fn):
        CHECKS.append((name, fn, fix))
        return fn
    return deco


@check("repository",
       "The session was started without a git source. A scheduled Routine "
       "created through the MCP tool does NOT carry one — it inherits the "
       "environment, not the repo. Create the Routine from the claude.ai "
       "Routines UI with the repository attached, or bind it to a persistent "
       "session created with source_url. An unattended session cannot clone "
       "its way out: the repo is private and `git clone` needs a permission "
       "approval no one is there to give.")
def _repository():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT,
                              capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return False, f"{ROOT} is not a git work tree — no repo, no risk engine"

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == "HEAD":
        return False, "detached HEAD; a session cannot push its state from here"

    remotes = git("remote").stdout.split()
    if "origin" not in remotes:
        return False, "no 'origin' remote; state could be written but never pushed"

    # Auth against the private repo is what actually has to work — a readable
    # working copy proves nothing about whether this session can persist to it.
    f = git("fetch", "origin", branch)
    if f.returncode != 0:
        return False, f"git fetch failed: {f.stderr.strip()[:110]}"

    behind = git("rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
    note = f" ({behind} commit(s) behind origin — pull first)" if behind not in ("", "0") else ""
    return True, f"on {branch}, origin reachable{note}"


@check("network policy",
       "See docs/08-network-policy.md. Network changes apply to a RUNNING "
       "session, so no restart is needed for this one.")
def _network():
    r = subprocess.run([sys.executable, "-m", "tools.netcheck"],
                       cwd=ROOT, capture_output=True, text=True)
    blocked = [l.split()[0] for l in r.stdout.splitlines() if " FAIL " in l]
    if r.returncode != 0:
        return False, f"REQUIRED host(s) blocked: {', '.join(blocked[:6])}"
    if blocked:
        # netcheck exits 0, so nothing required is down. Say it loudly anyway:
        # these sources will serve the brief nothing, and the brief has to
        # carry that as an explicit "unavailable" rather than quietly omit it.
        return True, (f"DEGRADED primary source(s): {', '.join(blocked[:6])} — "
                      f"record as unavailable in the brief and downgrade posture")
    return True, "all required and primary hosts reachable"


@check("broker credentials",
       "Add ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY to the environment, "
       "then START A NEW SESSION. Environment variables are copied once at "
       "session start; a running session never sees ones added afterwards.")
def _keys():
    have = bool(os.environ.get("ALPACA_API_KEY_ID")
                and os.environ.get("ALPACA_API_SECRET_KEY"))
    if not have:
        return False, "ALPACA keys not visible in this session"
    try:
        from adapters.alpaca import AlpacaAdapter
        a = AlpacaAdapter(live=False)
        acct = a.account()
        return True, (f"paper account reachable: equity ${acct['equity']:,.2f}, "
                      f"cash ${acct['cash']:,.2f}")
    except Exception as e:
        return False, f"keys present but rejected: {str(e)[:110]}"


@check("model routing",
       "Set TRADING_AGENT_MODEL and TRADING_AGENT_EFFORT in the environment "
       "(new session required). Without them, blocking tasks refuse to run.")
def _model():
    m, e = os.environ.get("TRADING_AGENT_MODEL"), os.environ.get("TRADING_AGENT_EFFORT")
    if not m:
        return False, "TRADING_AGENT_MODEL unset — cannot verify the running model"
    return True, f"{m} at effort {e or 'unset'}"


@check("risk engine tests", "Do not trade on a failing constitution. Fix first.")
def _tests():
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ROOT, capture_output=True, text=True)
    last = [l for l in r.stderr.splitlines() if l.startswith("Ran ")]
    return r.returncode == 0, (last[0] if last else "see output") + \
        (" — all passing" if r.returncode == 0 else " — FAILURES")


@check("account state", "Clear a halt before trading. LOCKED needs a human.")
def _state():
    from tools import state
    d = state.load()
    rs = d.get("risk_state", "NORMAL")
    return rs == "NORMAL", f"risk state {rs}, mode {d.get('mode')}"


@check("live data",
       "Alpaca bars are the primary source and the only one that gates "
       "trading. If Alpaca itself is failing, do not trade — every stop and "
       "every size is computed from this series.")
def _data():
    """Gate on Alpaca. Treat Yahoo as the cross-check it is.

    This used to call Yahoo alone, so a 429 from a keyless, undocumented
    endpoint exited non-zero and meant DO NOT TRADE for the day. That inverts
    the documented precedence — CLAUDE.md puts Alpaca first and calls Yahoo
    "fine as a cross-check, never the sole basis for a trade" — and it makes a
    rate limit on the fallback able to cancel a trading session.

    So: Alpaca decides. Yahoo is compared when it answers, because a silent
    disagreement between two sources is worth more than either number alone,
    and is simply reported absent when it does not.
    """
    try:
        from adapters.alpaca import AlpacaAdapter
        rows = AlpacaAdapter(live=False).bars("SPY", limit=25)
        if len(rows) < 20:
            return False, (f"Alpaca returned only {len(rows)} bars for SPY — "
                           f"too short to compute a 20-day lookback")
        last = rows[-1]
    except Exception as e:
        return False, f"Alpaca bars unavailable: {str(e)[:100]}"

    note = ""
    try:
        from adapters.marketdata import cross_check
        c = cross_check("SPY", last["close"])
        note = (f", cross-check {c['diff_bps']:.1f}bps"
                if c.get("agree") else
                f", !! CROSS-CHECK DISAGREES by {c['diff_bps']:.1f}bps — "
                f"stand down on this symbol")
    except Exception as e:
        note = f", cross-check unavailable ({type(e).__name__}) — not a blocker"

    return True, (f"SPY {len(rows)} bars through {last['date']}, "
                  f"last {last['close']:.2f}{note}")


def main() -> int:
    print("Phase 2 preflight\n" + "=" * 68)
    failures, warnings = [], []
    for name, fn, fix in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:                       # a check must never crash the run
            ok, detail = False, f"{type(e).__name__}: {str(e)[:90]}"
        warn = ok and detail.startswith("DEGRADED")
        mark = "XX " if not ok else ("!! " if warn else "ok ")
        print(f"  [{mark}] {name:22} {detail}")
        if not ok:
            failures.append((name, fix))
        elif warn:
            warnings.append((name, detail))

    print("=" * 68)
    if not failures:
        if warnings:
            print("READY, WITH DEGRADATION — these must reach the brief:\n")
            for name, detail in warnings:
                print(f"  {name}: {detail}")
            print("\nProceed, but the thesis is worth less than a clean day's. "
                  "Say which sources\nwere unavailable, by name, and downgrade "
                  "posture. Do not fill a gap from memory.")
            return 0
        print("READY. Start with the premarket-brief skill.")
        return 0
    print(f"NOT READY — {len(failures)} check(s) failed:\n")
    for name, fix in failures:
        print(f"  {name}\n    {fix}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
