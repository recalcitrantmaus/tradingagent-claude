#!/usr/bin/env python3
"""Verify the environment's network policy allows what the agent needs.

Run this after changing the cloud environment's network access. It tests every
host the agent depends on and tells you exactly which allowlist entries are
still missing.

    python3 -m tools.netcheck              # required hosts only
    python3 -m tools.netcheck --all        # include optional data/news hosts
    python3 -m tools.netcheck --domains    # print the allowlist to paste in

A host is "reachable" if the proxy permits the CONNECT. A 401/403 FROM THE API
(as opposed to the proxy) still counts as reachable — it means the network is
open and only the credentials are missing, which is the next problem, not this
one.

Reachable is not the same as usable. Some hosts answer HTTP 200 with a
JavaScript proof-of-work challenge instead of data; stooq.com does this now.
Those are reported DEGRADED, because an allowlist entry that returns a
challenge page is worse than a blocked one — it looks like it works.
"""
import argparse
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# (host, probe path, why it is needed, tier)
HOSTS: List[Tuple[str, str, str, str]] = [
    # ---- required: without these the agent cannot trade at all ----
    ("paper-api.alpaca.markets", "/v2/clock",
     "Alpaca paper trading — Phase 2 order routing", "required"),
    ("data.alpaca.markets", "/v2/stocks/SPY/bars?timeframe=1Day&limit=1",
     "Alpaca market data — prices, bars, the whole technical layer", "required"),
    ("api.alpaca.markets", "/v2/clock",
     "Alpaca live trading — Phase 3 only", "required"),
    ("agent.robinhood.com", "/mcp/trading",
     "Robinhood agentic MCP — Phase 3 order routing", "required"),

    # ---- primary sources: what news-intel ranks above every outlet ----
    ("www.sec.gov", "/cgi-bin/browse-edgar?action=getcompany",
     "SEC EDGAR filings — primary source for company facts", "primary"),
    ("www.federalreserve.gov", "/newsevents.htm",
     "Fed statements and calendar", "primary"),
    ("www.bls.gov", "/bls/newsrels.htm",
     "CPI, jobs — primary release, not a summary of one", "primary"),
    ("www.bea.gov", "/news/current-releases",
     "GDP, PCE", "primary"),
    ("home.treasury.gov", "/resource-center",
     "Yield curve, auctions", "primary"),
    ("www.finra.org", "/rules-guidance",
     "Day-trading and margin rules — verify before Phase 3", "primary"),

    # ---- optional: fallback data and crypto ----
    ("api.coingecko.com", "/api/v3/ping",
     "Crypto prices — free tier, no key", "optional"),
    ("stooq.com", "/q/d/l/?s=spy.us&i=d",
     "Free end-of-day history — a second opinion on Alpaca's bars", "optional"),
    ("query1.finance.yahoo.com", "/v8/finance/chart/SPY?range=5d&interval=1d",
     "Unofficial quote fallback", "optional"),
    ("docs.robinhood.com", "/crypto/trading/",
     "Robinhood crypto API reference", "optional"),

    # ---- optional: news outlets for WebFetch (WebSearch already works) ----
    ("www.reuters.com", "/markets/", "Wire coverage", "news"),
    ("apnews.com", "/hub/financial-markets", "Wire coverage", "news"),
    ("www.cnbc.com", "/markets/", "Market coverage", "news"),
    ("www.marketwatch.com", "/markets", "Market coverage", "news"),
    ("www.coindesk.com", "/markets", "Crypto-native coverage", "news"),
    ("www.theblock.co", "/", "Crypto-native coverage", "news"),
]

TIERS = {"required", "primary", "optional", "news"}


# Signatures of a bot-challenge page served with a 200.
CHALLENGE_MARKERS = (
    "requires JavaScript to verify your browser",
    "crypto.subtle.digest",
    "Checking your browser",
    "cf-browser-verification",
)


def user_agent() -> str:
    """The User-Agent to send to public data sources.

    Measured on 2026-09-17, because our own UA was the thing getting us
    blocked — not the egress allowlist:

        UA sent                                    dol.gov  bls.gov  sec.gov
        (none)                                         200      403      403
        tradingagent-claude                            403      403      403
        tradingagent-claude/1.0 (+<repo url>)          200      403      403
        tradingagent-claude (<an email address>)       200      200      200

    Only a contact-shaped UA carrying an email satisfies all three, which is
    also what SEC's access policy asks for by name. A browser UA was tried and
    is worse — 403 from dol.gov — so impersonation is neither necessary nor
    effective here, and it is not what this is.

    The address comes from TRADING_AGENT_CONTACT and is never defaulted to a
    personal one: it travels in an outbound header to third parties on every
    request, so whose address that is has to be a deliberate choice. Unset,
    the agent identifies itself without a contact and SEC, BLS and DOL will
    refuse it — netcheck then reports them DEGRADED, which is the honest
    outcome rather than a silent one.
    """
    contact = os.environ.get("TRADING_AGENT_CONTACT", "").strip()
    if contact:
        return f"tradingagent-claude/1.0 ({contact})"
    return "tradingagent-claude/1.0 (+https://github.com/recalcitrantmaus/tradingagent-claude)"


def probe(host: str, path: str, timeout: int = 12) -> Tuple[bool, str]:
    """Distinguish 'the proxy refused' from 'the API answered' from
    'the host answered with a bot challenge instead of data'."""
    url = f"https://{host}{path}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(4096).decode("utf-8", "replace")
            if any(m in body for m in CHALLENGE_MARKERS):
                return False, ("DEGRADED — HTTP 200 but served a JavaScript bot "
                               "challenge, not data. Reachable, not usable.")
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        # The host answered, but answering is not the same as serving data.
        # 401 and 429 mean the network is open and we lack a key or a quota —
        # a reachability check should pass those. 403 on a public page is a
        # WAF refusing this client, which is the stooq bot-challenge problem
        # wearing a different status code: reachable, not usable. Calling it
        # "ok" is how www.bls.gov sat green in preflight while returning
        # nothing to the brief for two sessions.
        if e.code == 403:
            return False, ("DEGRADED — HTTP 403. The host answered but refused "
                           "this client; it will return no data. Treat as "
                           "unavailable and say so in the brief.")
        return True, f"HTTP {e.code} (host answered — network is open)"
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "Tunnel connection failed" in reason or "403" in reason:
            return False, "BLOCKED by egress proxy (403 on CONNECT)"
        return False, f"unreachable: {reason[:70]}"
    except (socket.timeout, ssl.SSLError, TimeoutError) as e:
        return False, f"timeout/TLS: {str(e)[:70]}"


def allowlist(tiers: List[str]) -> List[str]:
    out = []
    for host, _, _, tier in HOSTS:
        if tier in tiers and host not in out:
            out.append(host)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="test every tier")
    ap.add_argument("--domains", action="store_true",
                    help="print the allowlist to paste into Allowed domains")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    tiers = list(TIERS) if a.all else ["required", "primary"]

    if a.domains:
        print("# Paste into the environment's Allowed domains "
              "(Network access -> Custom).")
        print("# Keep 'Also include default list of common package "
              "managers' CHECKED, or pip and npm stop working.\n")
        for h in allowlist(list(TIERS)):
            print(h)
        return 0

    results: Dict[str, Dict] = {}
    failed_required = 0
    degraded_primary: List[Tuple[str, str]] = []
    print(f"{'host':32} {'tier':9} {'status'}")
    print("-" * 92)
    for host, path, why, tier in HOSTS:
        if tier not in tiers:
            continue
        ok, detail = probe(host, path)
        results[host] = {"tier": tier, "ok": ok, "detail": detail, "why": why}
        mark = "ok  " if ok else "FAIL"
        print(f"{host:32} {tier:9} {mark} {detail}")
        if not ok:
            print(f"{'':32} {'':9}      needed for: {why}")
            if tier == "required":
                failed_required += 1
            elif tier == "primary":
                degraded_primary.append((host, why))

    if a.json:
        Path("sim/results/netcheck.json").write_text(json.dumps(results, indent=2))

    print()
    if degraded_primary:
        # A primary source that will not serve data is not a reason to stop
        # trading — it is a reason to trust the day's thesis less. Conflating
        # it with a broker outage is how a partial degradation turns into a
        # full stop, and how "say so and downgrade posture" quietly became
        # "halt". Both are wrong; these two states are kept apart.
        print(f"!! {len(degraded_primary)} PRIMARY source(s) degraded — "
              "reachable, but serving no data:")
        for host, why in degraded_primary:
            print(f"     {host} — {why}")
        print("   These do NOT block trading. They DO bind the brief: record "
              "each one as\n   'unavailable' by name and downgrade posture "
              "accordingly. Never fill the gap\n   from memory, and never "
              "present an unverified figure as sourced.")
        print("   A brief built on three blocked primaries is a NO_TRADE brief.\n")

    if failed_required:
        print(f"{failed_required} REQUIRED host(s) blocked. "
              "The agent cannot run Phase 2 until these open.")
        print("Fix: claude.ai/code -> cloud icon above the message box -> hover "
              "the environment -> settings gear\n     -> Network access: Custom "
              "-> paste `python3 -m tools.netcheck --domains` output into "
              "Allowed domains\n     -> keep 'Also include default list of "
              "common package managers' CHECKED -> Save changes.")
        print("Then start a NEW session — running sessions keep the old policy.")
        return 1
    if degraded_primary:
        print("All required hosts reachable. Primary-source degradation above "
              "is a posture input, not a stop.")
    else:
        print("All required hosts reachable. Network policy is good to go.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
