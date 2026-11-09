"""The five expected outputs of the brief, checked against a full demo run (collectors -> analysis -> exports -> HTML report)."""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


class ExpectedOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp()
        env = {**os.environ, "COORDWATCH_HOME": tempfile.mkdtemp(), "PYTHONPATH": ROOT}
        r = subprocess.run([sys.executable, "-m", "coordwatch", "run", "--topic", "Acme Bank", "--since", "2026-10-01",
                            "--until", "2026-10-14", "--source", "demo", "--out", cls.out], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        cls.res = json.load(open(os.path.join(cls.out, "results.json"), encoding="utf-8"))
        cls.html = open(os.path.join(cls.out, "report.html"), encoding="utf-8").read()

    def rows(self, name):
        return list(csv.DictReader(open(os.path.join(self.out, name), encoding="utf-8-sig")))

    def test_1_posts_with_text_media_date_engagement_link(self):
        posts = self.res["posts"]
        self.assertGreater(len(posts), 100)
        for p in posts[:50]:
            for k in ("text", "media", "created_at", "likes", "shares", "replies", "views", "url", "platform"):
                self.assertIn(k, p)
        self.assertTrue(any(m["type"] == "photo" for p in posts for m in p["media"]))
        cols = self.rows("posts.csv")[0].keys()
        for c in ("text", "photo_urls", "video_urls", "created_at", "likes", "shares", "replies", "views", "url"):
            self.assertIn(c, cols)
        self.assertTrue(all("2026-10-01" <= p["created_at"][:10] <= "2026-10-14" for p in posts))      # inside the date range

    def test_2_narratives_with_volume_over_time_and_per_platform(self):
        nars = [n for n in self.res["narratives"] if n["id"] >= 0]
        self.assertGreater(len(nars), 3)
        for n in nars:
            self.assertTrue(n["volume_over_time"] and n["volume_by_platform"] and n["keywords"] and n["label"])
        self.assertTrue(self.rows("volume_by_platform.csv"))
        self.assertIn("Main narratives", self.html)
        self.assertIn("Volume over time", self.html)

    def test_3_coordinated_groups_with_reasons(self):
        groups = self.res["coordinated_groups"]
        self.assertGreater(len(groups), 0)
        text = " ".join(" ".join(g["reasons"]) for g in groups)
        for needle in ("near-identical text", "within 5 min", "profile photo", "amplification"):
            self.assertIn(needle, text)                                   # same text, minutes apart, reused photos, amplifying each other
        self.assertTrue(any(g["signal_coverage"].get("created") for g in groups))   # accounts created around the same time
        self.assertIn("reasons", self.rows("coordinated_groups.csv")[0])
        self.assertIn("Why they're grouped", self.html)

    def test_4_origin_and_spread_per_narrative(self):
        origins = self.res["origins"]
        self.assertGreater(len(origins), 3)
        o = origins[0]
        self.assertTrue(o["first_accounts"] and o["first_post"] and o["platform_spread"])
        self.assertTrue({"account", "url", "at"} <= set(o["first_accounts"][0]))
        self.assertGreaterEqual(len({s["platform"] for oo in origins for s in oo["platform_spread"]}), 2)   # spread across platforms
        self.assertIn("first_account", self.rows("origins.csv")[0])
        self.assertIn("how it spread", self.html)

    def test_6_dashboard_summary_daily_counts_terms_and_plain_words_are_exported(self):
        ov = self.res["overview"]
        self.assertEqual(len(ov["days"]), 14)
        self.assertEqual(sum(d["total"] for d in ov["days"]), len(self.res["posts"]))
        self.assertEqual(ov["terms"][0]["posts"], len(self.res["posts"]))                 # every demo post mentions "acme bank"
        self.assertTrue(ov["plain"]["summary"] and ov["plain"]["narratives"] and ov["plain"]["groups"] and ov["plain"]["origins"])
        daily = self.rows("daily_counts.csv")
        self.assertEqual(len(daily), 14)
        self.assertIn("total_posts", daily[0])
        self.assertTrue(self.rows("term_mentions.csv") and self.rows("narrative_by_day.csv") and self.rows("narrative_by_term.csv"))
        txt = open(os.path.join(self.out, "plain_summary.txt"), encoding="utf-8").read()
        for head in ("SUMMARY IN SIMPLE WORDS", "WHAT PEOPLE ARE SAYING", "GROUPS OF ACCOUNTS", "WHERE EACH STORY STARTED"):
            self.assertIn(head, txt)
        for h in ("In plain words", "Posts per day", "Mentions per keyword", "Groups in simple words", "Where each story started"):
            self.assertIn(h, self.html)                                                   # also in the HTML report

    def test_5_exports_and_html_report(self):
        for f in ("results.json", "posts.csv", "narratives.csv", "coordinated_groups.csv", "origins.csv", "report.html"):
            self.assertTrue(os.path.getsize(os.path.join(self.out, f)) > 100, f)
        self.assertTrue(self.html.lstrip().lower().startswith("<!doctype html"))
        self.assertIsNone(re.search(r"https?://(?!demo\.invalid|www\.youtube|t\.me|x\.com|twitter)[a-z0-9.-]+/[^\"' ]*\.(js|css)", self.html), "report must work offline")


if __name__ == "__main__":
    unittest.main()


class ExecutivePdf(unittest.TestCase):
    def test_pdf_is_written_and_readable(self):
        from coordwatch.pdfreport import available
        if not available():
            self.skipTest("reportlab not installed")
        out = tempfile.mkdtemp()
        env = {**os.environ, "COORDWATCH_HOME": tempfile.mkdtemp(), "PYTHONPATH": ROOT}
        subprocess.run([sys.executable, "-m", "coordwatch", "run", "--topic", "Acme Bank", "--since", "2026-10-01", "--until", "2026-10-14", "--source", "demo", "--out", out],
                       check=True, capture_output=True, env=env)
        f = os.path.join(out, "executive_report.pdf")
        data = open(f, "rb").read()
        self.assertTrue(data.startswith(b"%PDF") and len(data) > 5000)
        self.assertNotIn(b"Data API", open(os.path.join(out, "report.html"), "rb").read())     # no collector warnings in the HTML report


class StoriesAndCombinedTerms(unittest.TestCase):
    def test_story_numbers_start_at_one_and_terms_are_also_searched_together(self):
        out = tempfile.mkdtemp()
        env = {**os.environ, "COORDWATCH_HOME": tempfile.mkdtemp(), "PYTHONPATH": ROOT}
        subprocess.run([sys.executable, "-m", "coordwatch", "run", "--topic", "Acme Bank, insolvent, withdraw", "--since", "2026-10-01", "--until", "2026-10-14",
                        "--source", "demo", "--out", out], check=True, capture_output=True, env=env)
        import json
        r = json.load(open(os.path.join(out, "results.json"), encoding="utf-8"))
        ids = sorted(n["id"] for n in r["narratives"] if n["id"] >= 0)
        self.assertEqual(ids[0], 1)
        self.assertEqual(ids, list(range(1, len(ids) + 1)))
        self.assertTrue(all(p["narrative_id"] != 0 for p in r["posts"]))
        terms = {t["term"]: t for t in r["overview"]["terms"]}
        self.assertIn("all terms together", terms)
        self.assertLessEqual(terms["all terms together"]["posts"], min(t["posts"] for k, t in terms.items() if k != "all terms together"))
        self.assertIn("Story 1", open(os.path.join(out, "plain_summary.txt"), encoding="utf-8").read())
        self.assertNotIn("#0", open(os.path.join(out, "plain_summary.txt"), encoding="utf-8").read())
