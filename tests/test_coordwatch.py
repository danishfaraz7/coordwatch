import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coordwatch import textutil
from coordwatch.collectors import demo
from coordwatch.collectors.base import HttpClient, PlatformBlocked, dhash_bytes
from coordwatch.collectors.fileimport import load_file
from coordwatch.collectors import x as xcol, youtube as ytcol, telegram as tgcol
from coordwatch.config import Config
from coordwatch.evaluate import score
from coordwatch.export import export_all
from coordwatch.filtering import matches_topic
from coordwatch.models import Post, parse_dt
from coordwatch.pipeline import analyse
from coordwatch.report import render

S = datetime(2026, 10, 1, tzinfo=timezone.utc)
U = datetime(2026, 10, 14, 23, 59, tzinfo=timezone.utc)
_posts, _truth = demo.generate(42)
RESULT = analyse(_posts, "Acme Bank", S, U, None, Config(discount_verified=True))


class TextTests(unittest.TestCase):
    def test_normalize_strips_urls_mentions_emoji(self):
        self.assertEqual(textutil.normalize("🚨 BREAKING @bob https://x.co/a Acme-Bank!!"), ["breaking", "acme", "bank"])

    def test_near_duplicates_found_and_distinct_texts_not(self):
        t = [textutil.normalize(x) for x in [
            "BREAKING: Acme Bank is INSOLVENT. Withdraw your savings NOW before it's too late! #A",
            "🚨 BREAKING: Acme Bank is insolvent - withdraw your savings now before it's too late #B",
            "My banking app has been down since this morning and support is jammed again today"]]
        cl = textutil.near_duplicate_clusters(t, 0.6)
        self.assertEqual(cl, [[0, 1]])

    def test_short_posts_never_duplicates(self):
        t = [textutil.normalize("lol"), textutil.normalize("lol")]
        self.assertEqual(textutil.near_duplicate_clusters(t), [])


class FilterTests(unittest.TestCase):
    def test_topic_matching(self):
        self.assertTrue(matches_topic("so #AcmeBank is trending", "Acme Bank"))
        self.assertTrue(matches_topic("Collapse of acme bank", '"Acme Bank" OR #AcmeBankCollapse'))
        self.assertFalse(matches_topic("totally different", "Acme Bank"))

    def test_date_parsing(self):
        self.assertEqual(parse_dt("2026-10-01T10:00:00Z"), datetime(2026, 10, 1, 10, tzinfo=timezone.utc))
        self.assertEqual(parse_dt(1790000000).tzinfo, timezone.utc)
        self.assertEqual(parse_dt(1790000000000), parse_dt(1790000000))


class LiveFilterTests(unittest.TestCase):
    def test_topic_filter_can_be_disabled_for_live_sources(self):
        c = Post(id="1", platform="youtube", author_id="a", author_name="a", text="great phone honestly", created_at=S + timedelta(hours=1))
        self.assertEqual(len(analyse([c], "iPhone 17", S, U, None, Config(), topic_filter=False)["posts"]), 1)
        with self.assertRaises(SystemExit):
            analyse([c], "iPhone 17", S, U, None, Config())


class PipelineTests(unittest.TestCase):
    def test_output_has_required_parts(self):
        for k in ("posts", "narratives", "coordinated_groups", "origins", "volume", "meta"):
            self.assertIn(k, RESULT)
        p = RESULT["posts"][0]
        for k in ("text", "media", "created_at", "likes", "shares", "replies", "url", "platform"):
            self.assertIn(k, p)
        self.assertTrue(all(g["reasons"] for g in RESULT["coordinated_groups"]))

    def test_accuracy_floor_on_synthetic_truth(self):
        s = score(RESULT, _truth)
        self.assertGreaterEqual(s["precision"], 0.95)
        self.assertGreaterEqual(s["recall"], 0.9)
        self.assertEqual(s["decoys"]["decoy_meme"]["wrongly_flagged"], 0)   # viral single text must not group people

    def test_known_false_positive_without_verified_discount(self):
        r = analyse(_posts, "Acme Bank", S, U, None, Config())
        s = score(r, _truth)
        self.assertEqual(s["decoys"]["decoy_newswire"]["wrongly_flagged"], 5)  # documented limitation

    def test_origin_points_at_botnet_seed_on_telegram_first(self):
        nid = next(n["id"] for n in RESULT["narratives"] if "insolvent" in n["keyword_label"])
        o = next(o for o in RESULT["origins"] if o["narrative_id"] == nid)
        self.assertEqual(o["first_post"]["platform"], "telegram")
        self.assertEqual([s["platform"] for s in o["platform_spread"]][:2], ["telegram", "x"])
        self.assertIsNotNone(o["seeding_group"])

    def test_single_default_avatar_is_not_evidence(self):
        accts = [Post(id=str(i), platform="x", author_id=f"u{i}", author_name=f"u{i}", created_at=S + timedelta(days=i),
                      text=f"Acme Bank thing number {i} happened unique words {i*7}", avatar_hash="0f" * 8) for i in range(30)]
        r = analyse(accts, "Acme Bank", S, U, None, Config())
        self.assertEqual(r["coordinated_groups"], [])

    def test_html_report_escapes_untrusted_text(self):
        evil = Post(id="1", platform="x", author_id="a", author_name="<script>alert(1)</script>",
                    text="Acme Bank <img src=x onerror=alert(1)> payload more words here", created_at=S + timedelta(hours=1))
        html = render(analyse([evil] * 1 + _posts[:30], "Acme Bank", S, U, None, Config()))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)

    def test_exports(self):
        with tempfile.TemporaryDirectory() as d:
            paths = export_all(RESULT, d)
            self.assertTrue(all(os.path.getsize(p) > 0 for p in paths))
            with open(os.path.join(d, "posts.csv"), newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), RESULT["meta"]["n_posts"])
            self.assertEqual(json.load(open(os.path.join(d, "results.json"), encoding="utf-8"))["meta"]["topic"], "Acme Bank")


class CollectorTests(unittest.TestCase):
    def test_x_parser(self):
        payload = {"data": [{"id": "10", "author_id": "7", "text": "RT @a: Acme Bank is done", "created_at": "2026-10-04T08:00:00.000Z",
                             "public_metrics": {"like_count": 2, "retweet_count": 3, "reply_count": 1, "quote_count": 1, "impression_count": 99},
                             "referenced_tweets": [{"type": "retweeted", "id": "9"}],
                             "attachments": {"media_keys": ["m1"]}}],
                   "includes": {"users": [{"id": "7", "username": "bob", "created_at": "2026-09-30T00:00:00.000Z",
                                           "public_metrics": {"followers_count": 5}, "profile_image_url": "https://pbs/x_normal.jpg"}],
                                "media": [{"media_key": "m1", "type": "photo", "url": "https://pbs/p.jpg"}],
                                "tweets": [{"id": "9", "author_id": "3", "text": "Acme Bank is done (full original text)"}]}}
        p = xcol.parse_response(payload)[0]
        self.assertTrue(p.is_reshare)
        self.assertEqual((p.reshare_of, p.reshare_of_author, p.shares, p.views), ("9", "3", 4, 99))
        self.assertEqual(p.text, "Acme Bank is done (full original text)")
        self.assertEqual(p.url, "https://x.com/bob/status/10")
        self.assertEqual(p.media[0]["type"], "photo")

    def test_youtube_parsers(self):
        ch = {"UC1": {"publishedAt": "2026-09-25T00:00:00Z", "avatar_hash": "ab" * 8}}
        c = ytcol.parse_comment({"snippet": {"totalReplyCount": 2, "topLevelComment": {"id": "c1", "snippet": {
            "authorChannelId": {"value": "UC1"}, "authorDisplayName": "Z", "textOriginal": "Acme Bank is insolvent",
            "publishedAt": "2026-10-05T10:00:00Z", "likeCount": 4}}}}, "vid", ch)
        self.assertEqual((c.account, c.likes, c.replies, c.avatar_hash), ("youtube:UC1", 4, 2, "ab" * 8))
        self.assertEqual(c.author_created.year, 2026)

    def test_telegram_message_conversion(self):
        m = SimpleNamespace(id=5, message="Acme Bank news", date=datetime(2026, 10, 4, 8, tzinfo=timezone.utc), post=True, sender_id=None,
                            views=100, forwards=3, replies=SimpleNamespace(replies=2), reactions=SimpleNamespace(results=[SimpleNamespace(count=4)]),
                            fwd_from=SimpleNamespace(from_id=SimpleNamespace(channel_id=99), channel_post=12), photo=object(), video=None, gif=None)
        p = tgcol.message_to_post(m, "chan", "123", "Chan")
        self.assertEqual((p.platform, p.author_id, p.likes, p.shares, p.replies, p.views), ("telegram", "123", 4, 3, 2, 100))
        self.assertEqual(p.reshare_of_author, "99")
        self.assertEqual(p.url, "https://t.me/chan/5")

    def test_file_import_alias_mapping_tiktok_like(self):
        row = {"id": "7", "text": "Acme Bank scandal", "createTimeISO": "2026-10-03T10:00:00.000Z", "authorMeta": {"name": "tt_user", "id": "88", "fans": 12},
               "diggCount": 10, "shareCount": 2, "commentCount": 1, "playCount": 500, "webVideoUrl": "https://tiktok.com/@tt_user/video/7"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([row], f)
        p = load_file(f.name, "tiktok")[0]
        os.unlink(f.name)
        self.assertEqual((p.platform, p.author_name, p.likes, p.shares, p.views, p.author_followers), ("tiktok", "tt_user", 10, 2, 500, 12))

    def test_dhash_is_stable_under_resize(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow missing")
        import io
        im = Image.new("RGB", (200, 200), "white")
        d = ImageDraw.Draw(im); d.ellipse((30, 30, 150, 170), fill="black"); d.rectangle((100, 10, 190, 60), fill="gray")
        b1, b2 = io.BytesIO(), io.BytesIO()
        im.save(b1, "PNG"); im.resize((90, 90)).save(b2, "JPEG")
        h1, h2 = dhash_bytes(b1.getvalue()), dhash_bytes(b2.getvalue())
        self.assertLessEqual(bin(int(h1, 16) ^ int(h2, 16)).count("1"), 6)


class CalibrationTests(unittest.TestCase):
    def test_few_accounts_sharing_one_generic_message_are_not_high_confidence(self):
        from datetime import datetime, timezone, timedelta
        base = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        posts = []
        for i in range(3):      # three unrelated commenters happen to paste the same generic sentence minutes apart
            posts.append(Post(id=f"g{i}", platform="youtube", author_id=f"u{i}", author_name=f"u{i}", created_at=base + timedelta(minutes=i),
                              text="great video thanks for sharing this with everyone", author_created=base - timedelta(days=2)))
        for i in range(40):     # background chatter
            posts.append(Post(id=f"b{i}", platform="youtube", author_id=f"b{i}", author_name=f"b{i}", created_at=base + timedelta(hours=i % 5, minutes=i),
                              text=f"payroll numbers discussion post number {i} with unique words {i * 13} {i * 7}"))
        r = analyse(posts, "payroll", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 9, tzinfo=timezone.utc), None, Config(), topic_filter=False)
        for g in r["coordinated_groups"]:
            self.assertNotEqual(g["confidence"], "high", g)

    def test_short_generic_comments_never_count_as_copy_paste(self):
        from datetime import datetime, timezone, timedelta
        base = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        posts = [Post(id=f"s{i}", platform="youtube", author_id=f"u{i}", author_name=f"u{i}", created_at=base + timedelta(seconds=20 * i),
                      text="thanks for sharing this") for i in range(8)]
        posts += [Post(id=f"b{i}", platform="youtube", author_id=f"b{i}", author_name=f"b{i}", created_at=base + timedelta(hours=i),
                       text=f"unrelated longer comment about the jobs report number {i} and wages {i * 3}") for i in range(20)]
        r = analyse(posts, "x", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 9, tzinfo=timezone.utc), None, Config(), topic_filter=False)
        self.assertEqual(r["coordinated_groups"], [])


class FutureWindowTests(unittest.TestCase):
    def test_youtube_never_queries_the_future(self):
        from datetime import datetime, timezone, timedelta
        seen = []

        class FakeClient:
            def get_json(self, url, params=None, headers=None):
                if url.endswith("/search"):
                    seen.append(params)
                return {"items": []}
        c = ytcol.YouTubeCollector(api_key="k", client=FakeClient())
        now = datetime.now(timezone.utc)
        c.collect("x", now - timedelta(days=3), now + timedelta(days=2))      # range extends into the future
        self.assertTrue(seen)
        for p in seen:
            self.assertLess(p["publishedAfter"], now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            self.assertLess(p["publishedAfter"], p["publishedBefore"])
            self.assertLessEqual(p["publishedBefore"], now.strftime("%Y-%m-%dT%H:%M:%SZ"))


class ProgressAndAbortTests(unittest.TestCase):
    def _yt(self, cancel_after=None):
        from coordwatch.collectors.base import Cancelled
        calls = {"n": 0}
        logs = []

        class FakeClient:
            notify = None
            cancelled = None
            s = None

            def get_json(self_, url, params=None, headers=None):
                calls["n"] += 1
                if cancel_after and calls["n"] > cancel_after:
                    flag["x"] = True
                if url.endswith("/search"):
                    return {"items": [{"id": {"videoId": f"v{params['publishedAfter'][8:10]}"}}]}
                if url.endswith("/videos"):
                    return {"items": [{"id": i, "snippet": {"channelId": "UC1", "channelTitle": "c", "title": "t", "description": "d",
                                                            "publishedAt": "2026-10-02T10:00:00Z"}, "statistics": {}} for i in params["id"].split(",")]}
                if url.endswith("/commentThreads"):
                    return {"items": [{"snippet": {"totalReplyCount": 0, "topLevelComment": {"id": "c" + params["videoId"], "snippet": {
                        "authorChannelId": {"value": "UC2"}, "authorDisplayName": "a", "textOriginal": "hi there", "publishedAt": "2026-10-02T11:00:00Z", "likeCount": 1}}}}]}
                if url.endswith("/channels"):
                    return {"items": [{"id": i, "snippet": {"publishedAt": "2026-01-01T00:00:00Z", "thumbnails": {}}} for i in params["id"].split(",")]}
                return {}
        flag = {"x": False}
        c = ytcol.YouTubeCollector(api_key="k", client=FakeClient(), hash_avatars=False, max_videos=6)
        c.log, c.cancelled = logs.append, (lambda: flag["x"])
        return c, logs, Cancelled

    def test_youtube_reports_each_step(self):
        from datetime import datetime, timezone
        c, logs, _ = self._yt()
        posts = c.collect("x", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 3, 23, tzinfo=timezone.utc))
        text = "\n".join(logs)
        for needle in ("searching videos", "fetching their statistics", "downloading comments", "comments 1/", "channel profiles", "done"):
            self.assertIn(needle, text)
        self.assertGreater(len(posts), 0)

    def test_youtube_abort_midway(self):
        from datetime import datetime, timezone
        c, logs, Cancelled = self._yt(cancel_after=2)
        with self.assertRaises(Cancelled):
            c.collect("x", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 5, tzinfo=timezone.utc))

    def test_http_retry_is_reported_and_abortable(self):
        from coordwatch.collectors.base import Cancelled
        msgs = []
        c = HttpClient(min_interval=0, session=FakeSession([FakeResp(429, headers={"Retry-After": "30"})] * 3), sleep=lambda s: None)
        c.notify = msgs.append
        flag = {"x": False}
        c.cancelled = lambda: flag["x"]
        flag["x"] = True
        with self.assertRaises(Cancelled):
            c.get_json("http://t")
        flag["x"] = False
        c2 = HttpClient(min_interval=0, session=FakeSession([FakeResp(429, headers={"Retry-After": "2"}), FakeResp(200, {"ok": 1})]), sleep=lambda s: None)
        c2.notify = msgs.append
        self.assertEqual(c2.get_json("http://t"), {"ok": 1})
        self.assertTrue(any("waiting" in m for m in msgs))


class FakeResp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._b, self.headers, self.text = code, body or {}, headers or {}, "x"

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), 0

    def get(self, *a, **k):
        self.calls += 1
        return self.seq.pop(0)


class RateLimitTests(unittest.TestCase):
    def test_backoff_honours_retry_after_then_succeeds(self):
        sleeps = []
        c = HttpClient(min_interval=0, session=FakeSession([FakeResp(429, headers={"Retry-After": "7"}), FakeResp(503), FakeResp(200, {"ok": 1})]),
                       sleep=sleeps.append)
        self.assertEqual(c.get_json("http://t"), {"ok": 1})
        self.assertIn(8.0, sleeps)
        self.assertEqual(c.stats["retries"], 2)

    def test_auth_failure_is_not_retried(self):
        s = FakeSession([FakeResp(403)])
        with self.assertRaises(PlatformBlocked):
            HttpClient(min_interval=0, session=s, sleep=lambda _: None).get_json("http://t")
        self.assertEqual(s.calls, 1)

    def test_gives_up_after_max_retries_with_clear_error(self):
        c = HttpClient(min_interval=0, max_retries=2, session=FakeSession([FakeResp(429)] * 3), sleep=lambda _: None)
        with self.assertRaises(PlatformBlocked):
            c.get_json("http://t")

    def test_disk_cache_avoids_second_call(self):
        with tempfile.TemporaryDirectory() as d:
            s = FakeSession([FakeResp(200, {"a": 1})])
            c = HttpClient(min_interval=0, session=s, cache_dir=d, sleep=lambda _: None)
            c.get_json("http://t", {"q": 1}); c.get_json("http://t", {"q": 1})
            self.assertEqual((s.calls, c.stats["cache_hits"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
