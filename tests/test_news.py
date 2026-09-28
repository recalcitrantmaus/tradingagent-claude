import contextlib
import io
import unittest
import urllib.error

from tools import news

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Rates hold</title><link>https://example.org/a</link>
<pubDate>Mon, 28 Sep 2026 16:09:05 GMT</pubDate></item>
<item><title>No link</title></item>
<item><title>Second</title><link>https://example.org/b</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom one</title><link href="https://example.org/c"/>
<updated>2026-09-28T10:00:00Z</updated></entry></feed>"""


def run(argv, get):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = news.main(argv, get=get)
    return rc, buf.getvalue()


class ParseTest(unittest.TestCase):
    def test_rss_items_need_a_title_and_a_link(self):
        items = news.parse(RSS, 10)
        self.assertEqual([t for t, _, _ in items], ["Rates hold", "Second"])
        self.assertEqual(items[0][2], "2026-09-28T16:09Z")
        self.assertEqual(items[1][2], "")

    def test_atom_link_is_read_from_href(self):
        self.assertEqual(news.parse(ATOM, 10)[0][1], "https://example.org/c")

    def test_limit(self):
        self.assertEqual(len(news.parse(RSS, 1)), 1)


class MainTest(unittest.TestCase):
    def test_bbc_and_guardian_are_fetched(self):
        urls = {u for _, _, u in news.FEEDS}
        self.assertIn("https://feeds.bbci.co.uk/news/business/rss.xml", urls)
        self.assertIn("https://www.theguardian.com/uk/business/rss", urls)

    def test_all_ok_exits_zero(self):
        rc, out = run([], lambda u: RSS)
        self.assertEqual(rc, 0)
        self.assertIn("Rates hold", out)

    def test_a_dead_feed_is_reported_not_filled_in(self):
        def get(u):
            if "guardian" in u:
                raise urllib.error.URLError("refused")
            return RSS
        rc, out = run(["--lane", "left"], get)
        self.assertEqual(rc, 0)          # NPR still covers the lane
        self.assertIn("Guardian business: UNAVAILABLE", out)

    def test_an_empty_lane_exits_one(self):
        def get(u):
            raise urllib.error.URLError("refused")
        rc, out = run(["--lane", "left"], get)
        self.assertEqual(rc, 1)
        self.assertIn("LANES WITH NO ITEMS: left", out)


if __name__ == "__main__":
    unittest.main()
