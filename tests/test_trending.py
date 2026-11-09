import unittest
from datetime import datetime, timezone

from coordwatch.trending import terms_from, trending

TRENDS = """<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>India vs New Zealand</title><ht:approx_traffic>200,000+</ht:approx_traffic></item>
<item><title>Budget 2026</title><ht:approx_traffic>50,000+</ht:approx_traffic></item></channel></rss>"""
NEWS = "<rss><channel><item><title>India vs New Zealand: Kohli leads chase #INDvNZ</title></item><item><title>Kohli hits ton as India beat New Zealand</title></item></channel></rss>"
TG = """<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chan/5"><div class="tgme_widget_message_text">Big win #INDvNZ tonight</div>
<a class="tgme_widget_message_date" href="https://t.me/chan/5"><time datetime="2026-11-07T10:00:00+00:00"></time></a><span class="tgme_widget_message_views">1.2K</span></div></div>"""


def fake(url):
    if "trends.google" in url: return TRENDS
    if "news.google" in url: return NEWS
    if "gdelt" in url: raise OSError("blocked")
    if "t.me" in url: return TG
    raise OSError(url)


class TrendingTests(unittest.TestCase):
    def test_terms_prefer_hashtags_and_phrases_and_drop_substrings(self):
        t = terms_from([("India vs New Zealand #INDvNZ", 5), ("India beat New Zealand", 3)])
        names = [x["term"] for x in t]
        self.assertIn("#indvnz", [n.lower() for n in names])
        self.assertIn("India vs New Zealand", names)
        self.assertNotIn("New Zealand", names)

    def test_each_source_fails_on_its_own(self):
        a, b = datetime(2026, 11, 6, tzinfo=timezone.utc), datetime(2026, 11, 8, tzinfo=timezone.utc)
        out = trending(a, b, "IN", ["@chan"], get=fake, yt_search=lambda term: [{"title": f"{term} highlights #INDvNZ", "view_count": 900}])
        ids = [s["id"] for s in out["sources"]]
        self.assertEqual(ids, ["web", "youtube", "telegram"])
        web = out["sources"][0]
        self.assertEqual(web["items"][0]["term"], "India vs New Zealand")
        self.assertIn("GDELT unavailable", web["note"])
        self.assertTrue(any("indvnz" in i["term"].lower() for i in out["sources"][1]["items"]))
        self.assertTrue(any("indvnz" in i["term"].lower() for i in out["sources"][2]["items"]))

    def test_telegram_without_channels_explains_what_to_do(self):
        a = datetime(2026, 11, 6, tzinfo=timezone.utc)
        out = trending(a, a, "IN", [], platforms=("telegram",), get=fake)
        self.assertEqual(out["sources"][0]["items"], [])
        self.assertIn("channels", out["sources"][0]["note"])

    def test_youtube_failure_is_reported_not_raised(self):
        a = datetime(2026, 11, 6, tzinfo=timezone.utc)
        def boom(term): raise RuntimeError("no network")
        out = trending(a, a, "IN", [], platforms=("web", "youtube"), get=fake, yt_search=boom)
        self.assertIn("Could not read YouTube", out["sources"][1]["note"])


if __name__ == "__main__":
    unittest.main()
