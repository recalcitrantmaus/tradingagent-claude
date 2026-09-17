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
     "Alpaca market data AND the news API (/v1beta1/news) — prices, bars, "
     "and symbol-tagged headlines from an authenticated source", "required"),
    ("api.alpaca.markets", "/v2/clock",
     "Alpaca live trading — Phase 3 only", "required"),
    ("agent.robinhood.com", "/mcp/trading",
     "Robinhood agentic MCP — Phase 3 order routing", "required"),

    # ---- primary: verified serving 200 on 2026-09-17 with the contact UA ----
    ("www.sec.gov", "/cgi-bin/browse-edgar?action=getcompany",
     "SEC EDGAR filings — primary source for company facts", "primary"),
    ("www.federalreserve.gov", "/newsevents.htm",
     "Fed statements and calendar", "primary"),
    ("www.bls.gov", "/bls/newsrels.htm",
     "CPI, jobs — primary release, not a summary of one", "primary"),
    ("www.bea.gov", "/news/current-releases", "GDP, PCE", "primary"),
    ("home.treasury.gov", "/", "Yield curve, auctions", "primary"),
    ("www.finra.org", "/rules-guidance",
     "Day-trading and margin rules — verify before Phase 3", "primary"),

    # ---- optional: verified working fallbacks ----
    ("api.coingecko.com", "/api/v3/ping",
     "Crypto prices — free tier, no key", "optional"),
    ("query1.finance.yahoo.com", "/v8/finance/chart/SPY?range=5d&interval=1d",
     "Independent price cross-check. Rate-limits under load, so it must never "
     "gate a trading day — see docs/04-lessons.md 2026-09-17", "optional"),
    ("www.coindesk.com", "/markets",
     "Crypto-native coverage — the one news HTML host that serves us", "optional"),
    ("docs.robinhood.com", "/crypto/trading/",
     "Robinhood crypto API reference", "optional"),

    # ---- proposed: NOT yet allowlisted, so NOT yet verified ----
    # Everything below returned "proxy blocked CONNECT" on 2026-09-17, meaning
    # the egress policy refused before the host was ever asked. Their status is
    # therefore UNKNOWN, not good. Add them to the allowlist and re-run
    # `python3 -m tools.netcheck --all`; promote to primary only what answers.
    #
    # Ranked by how likely a non-browser client is to be served. Machine-
    # readable government endpoints are built for programmatic access and
    # almost always serve; consumer news HTML mostly does not, which is why
    # the old news tier is gone rather than expanded.
    ("data.sec.gov", "/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json",
     "SEC structured company facts as JSON — a different host from www.sec.gov",
     "proposed"),
    ("fred.stlouisfed.org", "/graph/fredgraph.csv?id=ICSA",
     "FRED macro series as CSV, no key — jobless claims, yields, spreads. "
     "Covers the DOL claims print that started this", "proposed"),
    ("api.fiscaldata.treasury.gov",
     "/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?page[size]=1",
     "Treasury fiscal data as JSON", "proposed"),
    ("www.newyorkfed.org", "/markets/reference-rates/sofr",
     "SOFR and reference rates — the rate that actually clears", "proposed"),
    ("publicreporting.cftc.gov", "/resource/6dca-aqww.json?$limit=1",
     "CFTC Commitments of Traders — positioning", "proposed"),
    ("api.census.gov", "/data/timeseries/eits/marts?get=cell_value&time=2026",
     "Census retail sales", "proposed"),
    ("www.eia.gov", "/petroleum/supply/weekly/",
     "EIA energy inventories", "proposed"),

    # RSS rather than the HTML page: feeds are meant for machines and usually
    # serve a non-browser client where the site itself throws a challenge.
    # These carry the political spread the news-intel skill asks for.
    ("feeds.bbci.co.uk", "/news/business/rss.xml", "BBC business RSS", "proposed"),
    ("feeds.npr.org", "/1006/rss.xml", "NPR business RSS", "proposed"),
    ("www.theguardian.com", "/uk/business/rss", "Guardian business RSS", "proposed"),
    ("moxie.foxbusiness.com", "/google-publisher/markets.xml",
     "Fox Business markets RSS", "proposed"),
    ("thehill.com", "/business/feed/", "The Hill business RSS", "proposed"),
    ("cointelegraph.com", "/rss", "Cointelegraph RSS", "proposed"),
    ("decrypt.co", "/feed", "Decrypt RSS", "proposed"),

    # ---- REMOVED 2026-09-17, all verified dead, kept here as a record ----
    # Do not re-add without re-testing; each was reported healthy for weeks.
    #   stooq.com            HTTP 200 + JS bot challenge
    #   www.reuters.com      HTTP 401 + JS bot challenge
    #   www.marketwatch.com  HTTP 401 + JS bot challenge
    #   apnews.com           HTTP 403 + JS bot challenge
    #   www.theblock.co      HTTP 403 + JS bot challenge
    #   www.cnbc.com         HTTP 403
    # Market news now comes from Alpaca's /v1beta1/news (authenticated,
    # symbol-tagged, already required) and from WebSearch, which works.
]

TIERS = {"required", "primary", "optional", "proposed"}


# Signatures of a bot-challenge page served with a 200.
CHALLENGE_MARKERS = (
    "requires JavaScript to verify your browser",
    "crypto.subtle.digest",
    "Checking your browser",
    "cf-browser-verification",
    # Akamai/PerimeterX serve their wall as a 401 with this inline animation.
    # reuters.com and marketwatch.com both did, and both were reported "ok,
    # host answered" because the status code was inspected and the body was
    # not. A challenge is a challenge whatever number it arrives under.
    "#cmsg{animation",
    "_Incapsula_Resource",
    "__cf_chl",
    "challenge-platform",
    "Just a moment...",
    "enable JavaScript and cookies",
)


# Chosen by the account owner on 2026-09-17 for exactly this purpose. Public
# by design — it is transmitted to every data source we contact.
DEFAULT_CONTACT = "contact@set-via-env.invalid"


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

    The WAFs check only the *shape*: measured 2026-09-17, `nobody@nowhere.invalid`
    is accepted by all three and anything without an `@` is refused by all
    three. A fake address would therefore work. We use a real one anyway,
    because SEC's access policy asks for a contact so they can reach the
    operator if this traffic causes a problem, and answering that with a dead
    letterbox would be functional and dishonest — a bad trade for no benefit.

    The contact is committed rather than left to an environment variable.
    It is not a secret: it goes to third parties in a header on every single
    request, so the repository is not telling anyone anything the wire does
    not. Committing it also means a freshly-fired scheduled session is
    correctly identified without depending on an env var someone has to
    remember to set. TRADING_AGENT_CONTACT still overrides it.
    """
    contact = os.environ.get("TRADING_AGENT_CONTACT", "").strip() or DEFAULT_CONTACT
    return f"tradingagent-claude/1.0 ({contact})"


def probe(host: str, path: str, timeout: int = 30) -> Tuple[bool, str]:
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
        # Inspect the BODY, not just the status. A bot wall served as 401 is
        # still a bot wall, and status-only inspection is what made two dead
        # news sources read as healthy.
        try:
            body = e.read(4096).decode("utf-8", "replace")
        except Exception:
            body = ""
        if any(m in body for m in CHALLENGE_MARKERS):
            return False, (f"DEGRADED — HTTP {e.code} carrying a JavaScript bot "
                           f"challenge, not data. Reachable, not usable.")
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
