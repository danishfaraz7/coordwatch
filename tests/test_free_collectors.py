"""Tests for the free (zero-cost) collection routes: yt-dlp, Telegram web preview, X browser payload parser,
discovery stage and the fallback chain.  No network: parsers run on recorded-shape fixtures."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coordwatch import collect, discovery
from coordwatch.collectors import telegram_web as tw, x_browser as xb, youtube_ytdlp as yd
from coordwatch.collectors.base import Collector, PlatformBlocked

S = datetime(2026, 10, 1, tzinfo=timezone.utc)
E = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)

TG_HTML = """
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="newsdesk/101">
 <div class="tgme_widget_message_text">Acme Bank is insolvent, withdraw now!</div>
 <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example/p1.jpg')"></a>
 <span class="tgme_widget_message_views">1.2K</span>
 <a class="tgme_widget_message_date"><time datetime="2026-10-05T10:00:00+00:00"></time></a></div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="newsdesk/102">
 <a class="tgme_widget_message_forwarded_from_name" href="https://t.me/origchan/77">Orig</a>
 <span class="tgme_widget_message_views">300</span>
 <a class="tgme_widget_message_date"><time datetime="2026-10-05T10:03:00+00:00"></time></a></div></div>
"""

XJSON = {"data": {"timeline": [{"tweet_results": {"result": {
    "rest_id": "111", "views": {"count": "5400"}, "is_blue_verified": False,
    "core": {"user_results": {"result": {"rest_id": "u1", "is_blue_verified": False,
             "core": {"screen_name": "alice", "created_at": "Mon Sep 28 08:00:00 +0000 2026"},
             "avatar": {"image_url": "https://pbs.example/a_normal.jpg"},
             "legacy": {"followers_count": 12, "default_profile_image": False}}}},
    "legacy": {"created_at": "Mon Oct 05 10:01:00 +0000 2026", "full_text": "Acme Bank is insolvent",
               "favorite_count": 3, "retweet_count": 2, "quote_count": 1, "reply_count": 0, "lang": "en",
               "extended_entities": {"media": [{"type": "photo", "media_url_https": "https://pbs.example/m.jpg"}]}}}}},
    {"tweet_results": {"result": {"__typename": "TweetWithVisibilityResults", "tweet": {
        "rest_id": "222",
        "core": {"user_results": {"result": {"rest_id": "u2", "core": {"screen_name": "bob"}, "legacy": {"default_profile_image": True}}}},
        "legacy": {"created_at": "Mon Oct 05 10:02:00 +0000 2026", "full_text": "RT @alice: Acme Bank is insolvent",
                   "retweeted_status_result": {"result": {"rest_id": "111", "core": {"user_results": {"result": {"rest_id": "u1"}}}}}}}}}}]}}


class YtDlp(unittest.TestCase):
    def test_video_and_comment_mapping(self):
        v = yd.map_video({"id": "abcDEF12345", "title": "Acme Bank run", "description": "d", "timestamp": 1790000000,
                          "channel_id": "UC1", "channel": "Chan", "view_count": 10, "like_count": 2, "comment_count": 3,
                          "thumbnail": "https://i.ytimg.com/x.jpg"})
        self.assertEqual((v.platform, v.author_id, v.views, v.replies), ("youtube", "UC1", 10, 3))
        self.assertEqual({m["type"] for m in v.media}, {"video", "photo"})
        c = yd.map_comment({"id": "Ug1", "text": "same text", "timestamp": 1790000100, "author_id": "UC9",
                            "author": "@bot9", "parent": "root", "like_count": 1}, "abcDEF12345")
        self.assertEqual((c.author_name, c.reply_to, c.author_id), ("bot9", "abcDEF12345", "UC9"))
        self.assertIsNone(yd.map_comment({"id": "x", "text": "  ", "timestamp": 1}, "v"))
        self.assertIsNone(yd.map_video({"id": "nodate"}))


class TelegramWeb(unittest.TestCase):
    def test_parse_page(self):
        posts = tw.parse_page(TG_HTML, "newsdesk")
        self.assertEqual([p.id for p in posts], ["newsdesk/101", "newsdesk/102"])
        a, b = posts
        self.assertEqual((a.views, a.media[0]["type"], a.is_reshare), (1200, "photo", False))
        self.assertTrue(b.is_reshare)
        self.assertEqual((b.reshare_of, b.reshare_of_author), ("origchan/77", "origchan"))

    def test_needs_channels(self):
        with self.assertRaises(RuntimeError):
            tw.TelegramWeb([])


class XBrowserParser(unittest.TestCase):
    def test_parse_payload(self):
        posts, avatars = xb.parse_search_payload(XJSON)
        by = {p.id: p for p in posts}
        self.assertEqual(set(by), {"111", "222"})
        a, b = by["111"], by["222"]
        self.assertEqual((a.author_name, a.shares, a.views, a.lang), ("alice", 3, 5400, "en"))
        self.assertEqual(a.author_created, datetime(2026, 9, 28, 8, tzinfo=timezone.utc))
        self.assertEqual(a.media[0]["type"], "photo")
        self.assertTrue(b.is_reshare and b.reshare_of == "111" and b.reshare_of_author == "u1" and b.avatar_is_default)
        self.assertIn("u1", avatars)

    def test_requires_cookies(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("X_COOKIES_FILE", None)
            with self.assertRaises(RuntimeError):
                xb.XBrowser(None)

    def test_garbage_payload_is_harmless(self):
        self.assertEqual(xb.parse_search_payload({"x": [1, {"tweet_results": {"result": {}}}]}), ([], {}))


class FakeBackend:
    def text(self, q, tl, n):
        if "site:t.me" in q:
            return [{"href": "https://t.me/s/leakchan/55", "title": "t", "body": "b"}, {"href": "https://t.me/joinchat/abc", "title": "x"}]
        if "site:youtube.com" in q:
            return [{"href": "https://www.youtube.com/watch?v=abcDEF12345", "title": "vid"}]
        raise RuntimeError("blocked")

    def news(self, q, tl, n):
        return [{"url": "https://news.example/a", "title": "Acme", "date": "2026-10-04T09:00:00+00:00", "source": "N"}]


class Discovery(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(discovery.telegram_channel("https://t.me/s/leakchan/55"), "leakchan")
        self.assertIsNone(discovery.telegram_channel("https://t.me/joinchat/abc"))
        self.assertEqual(discovery.youtube_id("https://youtu.be/abcDEF12345"), "abcDEF12345")
        self.assertEqual(discovery.classify("https://mobile.twitter.com/x"), "x")

    def test_discover_survives_blocked_queries(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("coordwatch.discovery.time.sleep"):
            r = discovery.discover("Acme Bank", S, E, d, backend=FakeBackend(), pause=(0, 0))
            self.assertEqual([c["channel"] for c in r["telegram_channels"]], ["leakchan"])
            self.assertEqual(r["youtube_video_ids"], ["abcDEF12345"])
            self.assertEqual(r["earliest_dated_mention"]["url"], "https://news.example/a")
            self.assertTrue(any(not q["ok"] for q in r["queries"]))      # blocked ones are logged, not fatal
            self.assertTrue(os.path.exists(os.path.join(d, "discovery.json")))


class Chain(unittest.TestCase):
    class Boom(Collector):
        platform = "youtube"
        notes = []

        def __init__(self, exc):
            self.exc = exc

        def collect(self, *a, **k):
            raise self.exc

    class Ok(Collector):
        platform = "youtube"
        notes = ["ok-note"]

        def collect(self, *a, **k):
            return ["post"]

    def _run(self, chain):
        notes = []
        with mock.patch.object(collect, "_chain", return_value=chain):
            got, used = collect._run_chain("youtube", "t", S, E, 10, "", False, "standard", lambda: False, lambda m: None, notes)
        return got, used, notes

    def test_falls_back_when_first_route_blocked_or_unconfigured(self):
        def unconfigured():
            raise RuntimeError("no key")
        got, used, notes = self._run([("API", lambda: self.Boom(PlatformBlocked("quota"))), ("nokey", unconfigured), ("free", self.Ok)])
        self.assertEqual((got, used), (["post"], "free"))
        self.assertTrue(any("API: BLOCKED" in n for n in notes) and any("nokey: not configured" in n for n in notes))
        self.assertIn("youtube: collected 1 posts via free.", notes)

    def test_all_routes_failing_is_reported_not_raised(self):
        got, used, notes = self._run([("a", lambda: self.Boom(ValueError("bad"))), ("b", lambda: self.Boom(RuntimeError("down")))])
        self.assertEqual((got, used), ([], None))
        self.assertTrue(notes[-1].startswith("youtube: skipped - no route worked"))


if __name__ == "__main__":
    unittest.main()
