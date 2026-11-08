import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
from datetime import datetime, timedelta, timezone

from coordwatch.models import Post
from coordwatch.pipeline import analyse

S = datetime(2026, 11, 4, tzinfo=timezone.utc)


def P(i, pl, h, text, url=""):
    return Post(id=str(i), platform=pl, author_id=f"{pl}{i}", author_name=f"{pl}{i}", text=text, created_at=S + timedelta(hours=h), url=url)


class CrossPlatformTests(unittest.TestCase):
    def test_links_lead_and_summary(self):
        posts = [P(0, "youtube", 1, "topg traders new video about gold setups", "https://www.youtube.com/watch?v=abcdefghijk")]
        for i in range(1, 9):
            posts.append(P(i, "youtube", 1 + i, f"topg traders gold setup breakdown number {i} liquidity", f"https://www.youtube.com/watch?v=vid{i:08d}"))
            posts.append(P(100 + i, "telegram", 3 + i, f"topg traders gold setup breakdown number {i} liquidity https://youtu.be/abcdefghijk"))
        posts.sort(key=lambda p: p.created_at)
        r = analyse(posts, "topg traders", None, None)
        cp = r["cross_platform"]
        self.assertTrue(cp["available"])
        self.assertEqual(cp["platforms"], ["telegram", "youtube"])
        self.assertTrue(cp["youtube_links_in_telegram"])
        self.assertEqual(cp["youtube_links_in_telegram"][0]["video_id"], "abcdefghijk")
        self.assertTrue(cp["youtube_links_in_telegram"][0]["telegram_after_video_hours"] > 0)
        self.assertTrue(any("Telegram post(s) link to YouTube" in x for x in cp["summary"]))
        self.assertIsNotNone(cp["volume_correlation"][0]["r"])

    def test_single_platform_says_so(self):
        posts = [P(i, "telegram", i, f"topg traders update {i}") for i in range(6)]
        cp = analyse(posts, "topg traders", None, None)["cross_platform"]
        self.assertFalse(cp["available"])
        self.assertIn("Only telegram", cp["summary"][0])


if __name__ == "__main__":
    unittest.main()


class TopicSeparatorTests(unittest.TestCase):
    def test_comma_separated_terms(self):
        from coordwatch.filtering import topic_terms, matches_topic
        self.assertEqual(topic_terms("MrBeast, #MrBeast"), ["mrbeast", "#mrbeast"])
        self.assertTrue(matches_topic("new #MrBeast video", "MrBeast, #MrBeast"))
        self.assertFalse(matches_topic("unrelated", "MrBeast, #MrBeast"))
