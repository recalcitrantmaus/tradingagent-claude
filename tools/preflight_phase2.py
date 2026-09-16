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
    if r.returncode == 0:
        return True, "all required and primary hosts reachable"
    blocked = [l.split()[0] for l in r.stdout.splitlines() if " FAIL " in l]
    return False, f"blocked: {', '.join(blocked[:6])}"


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


@check("live data", "Check netcheck; a DEGRADED source is unavailable.")
def _data():
    try:
        from adapters.marketdata import daily_bars
        b = daily_bars("SPY", rng="1mo")
        return True, f"SPY {len(b)} bars through {b[-1].date}, last {b[-1].close:.2f}"
    except Exception as e:
        return False, str(e)[:110]


def main() -> int:
    print("Phase 2 preflight\n" + "=" * 68)
    failures = []
    for name, fn, fix in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:                       # a check must never crash the run
            ok, detail = False, f"{type(e).__name__}: {str(e)[:90]}"
        print(f"  [{'ok ' if ok else 'XX '}] {name:22} {detail}")
        if not ok:
            failures.append((name, fix))

    print("=" * 68)
    if not failures:
        print("READY. Start with the premarket-brief skill.")
        return 0
    print(f"NOT READY — {len(failures)} check(s) failed:\n")
    for name, fix in failures:
        print(f"  {name}\n    {fix}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
