#!/usr/bin/env python3
"""Fetch the news-intel RSS feeds from inside the container.

    python3 -m tools.news              # every lane, 8 items per feed
    python3 -m tools.news --lane left  # one lane
    python3 -m tools.news --limit 20

G-3 (2026-09-28): `WebFetch` refuses feeds.bbci.co.uk and www.theguardian.com
("Claude Code is unable to fetch from ..."), while the container reaches both
with HTTP 200 (`tools.netcheck --all`). The refusal is the fetch tool's own
domain policy, not the environment's network policy, so the left lane rested
on NPR alone. Fetching here uses the container's network, the same path every
other adapter uses, and a named module can be allow-listed exactly.

Each feed prints ok or UNAVAILABLE. An unavailable feed is reported, never
filled in. Exit 1 when a whole lane came back empty, so a brief cannot claim
coverage of a lane it did not get.
"""
import argparse
import email.utils
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.netcheck import user_agent

# The RSS rows of the news-intel lane table. Keep the two in step.
FEEDS = (
    ("wire", "BBC business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("right", "Fox Business markets",
     "https://moxie.foxbusiness.com/google-publisher/markets.xml"),
    ("left", "Guardian business", "https://www.theguardian.com/uk/business/rss"),
    ("left", "NPR business", "https://feeds.npr.org/1006/rss.xml"),
    ("centrist", "The Hill business", "https://thehill.com/business/feed/"),
    ("crypto", "Cointelegraph", "https://cointelegraph.com/rss"),
    ("crypto", "Decrypt", "https://decrypt.co/feed"),
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    return urllib.request.urlopen(req, timeout=timeout).read()


def parse(raw: bytes, limit: int):
    """RSS 2.0 <item> or Atom <entry>: (title, link, published) tuples."""
    root = ET.fromstring(raw)
    out = []
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        f = {c.tag.rsplit("}", 1)[-1]: c for c in it}
        title = (f["title"].text or "").strip() if "title" in f else ""
        link = ""
        if "link" in f:
            link = (f["link"].text or f["link"].get("href") or "").strip()
        when = ""
        for k in ("pubDate", "published", "updated", "date"):
            if k in f and f[k].text:
                when = _iso(f[k].text.strip())
                break
        if title and link:
            out.append((title, link, when))
        if len(out) >= limit:
            break
    return out


def _iso(s: str) -> str:
    try:
        return email.utils.parsedate_to_datetime(s).strftime("%Y-%m-%dT%H:%MZ")
    except (TypeError, ValueError):
        return s


def main(argv=None, get=fetch) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane")
    ap.add_argument("--limit", type=int, default=8)
    a = ap.parse_args(argv)

    feeds = [f for f in FEEDS if a.lane in (None, f[0])]
    got = {}
    for lane, name, url in feeds:
        try:
            items = parse(get(url), a.limit)
        except (urllib.error.URLError, OSError, ET.ParseError) as e:
            print(f"## [{lane}] {name}: UNAVAILABLE ({e}) {url}\n")
            got.setdefault(lane, 0)
            continue
        got[lane] = got.get(lane, 0) + len(items)
        print(f"## [{lane}] {name}: ok, {len(items)} items  {url}")
        for title, link, when in items:
            print(f"- {when or 'undated'}  {title}\n  {link}")
        print()

    empty = sorted(l for l, n in got.items() if n == 0)
    if empty:
        print(f"LANES WITH NO ITEMS: {', '.join(empty)}. Say so in the brief.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
