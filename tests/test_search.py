import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from coordwatch.search import parse_query, search

ROOT = os.path.join(os.path.dirname(__file__), "..")


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = tempfile.mkdtemp()
        env = {**os.environ, "COORDWATCH_HOME": tempfile.mkdtemp(), "PYTHONPATH": ROOT}
        r = subprocess.run([sys.executable, "-m", "coordwatch", "run", "--topic", "Acme Bank", "--since", "2026-10-01", "--until", "2026-10-14",
                            "--source", "demo", "--out", out], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        cls.res = json.load(open(os.path.join(out, "results.json"), encoding="utf-8"))

    def test_parse_extracts_platform_date_and_intent(self):
        q = parse_query("Most liked YouTube posts about refunds on 7 Nov", datetime(2026, 11, 9, tzinfo=timezone.utc))
        self.assertEqual((q["platform"], q["day"], q["sort"]), ("youtube", "2026-11-07", "engagement"))
        self.assertEqual(q["words"], ["refund"])
        self.assertEqual(parse_query("telegrm 2026-10-05")["platform"], "telegram")          # typo in platform name
        self.assertEqual(parse_query("who posted first")["sort"], "earliest")
        self.assertEqual(parse_query("coordinated groups")["kind"], "groups")

    def test_filters_and_sorting(self):
        o = search(self.res, "most liked youtube posts about savings", 10)
        self.assertTrue(o["posts"] and all(p["platform"] == "youtube" for p in o["posts"]))
        eng = [p["engagement"] for p in o["posts"]]
        self.assertEqual(eng, sorted(eng, reverse=True))
        o = search(self.res, "posts on 2026-10-05", 50)
        self.assertTrue(o["posts"] and all(p["created_at"][:10] == "2026-10-05" for p in o["posts"]))
        o = search(self.res, "who posted first about insolvent", 5)
        ts = [p["created_at"] for p in o["posts"]]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(o["origins"])

    def test_typos_and_synonyms(self):
        self.assertTrue(search(self.res, "withdrawl")["posts"])                                # typo of withdrawal
        self.assertTrue(search(self.res, "coordinated groups")["groups"])
        self.assertEqual(search(self.res, "zzzqqq nothing")["posts"], [])


if __name__ == "__main__":
    unittest.main()
