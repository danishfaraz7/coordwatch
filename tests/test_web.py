import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_TMP = tempfile.mkdtemp()
os.environ["COORDWATCH_HOME"] = _TMP
for k in ("X_BEARER_TOKEN", "YOUTUBE_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"):
    os.environ.pop(k, None)

from coordwatch import secrets_store as S
from coordwatch.web import server as W


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        W.Handler.allow_hosts = []
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
        cls.port = cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, method, path, body=None, headers=None, raw=None):
        h = {"X-Coordwatch": "1"} if method == "POST" else {}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)


class SecretsTests(unittest.TestCase):
    def test_env_beats_file_and_delete(self):
        S.save({"YOUTUBE_API_KEY": "filekey", "NOT_A_KEY": "x"})
        self.assertEqual(S.get("YOUTUBE_API_KEY"), "filekey")
        self.assertEqual(S.status()["YOUTUBE_API_KEY"]["source"], "file")
        os.environ["YOUTUBE_API_KEY"] = "envkey"
        self.assertEqual(S.get("YOUTUBE_API_KEY"), "envkey")
        self.assertEqual(S.status()["YOUTUBE_API_KEY"]["source"], "env")
        del os.environ["YOUTUBE_API_KEY"]
        S.save({"YOUTUBE_API_KEY": ""})
        self.assertIsNone(S.get("YOUTUBE_API_KEY"))
        self.assertNotIn("NOT_A_KEY", json.dumps(S._load()))

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_file_is_owner_only(self):
        S.save({"X_BEARER_TOKEN": "t"})
        self.assertEqual(oct(os.stat(S._file()).st_mode & 0o777), "0o600")
        S.save({"X_BEARER_TOKEN": ""})


class WebTests(Base):
    def test_static_app_served_with_csp_and_no_inline_script(self):
        code, body, h = self.call("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("script-src 'self'", h.get("Content-Security-Policy", ""))
        self.assertNotIn(b"<script>", body)           # all JS is external so the CSP can forbid inline script
        self.assertEqual(self.call("GET", "/app.js")[0], 200)
        self.assertEqual(self.call("GET", "/../secrets_store.py")[0], 404)

    def test_status_never_leaks_values(self):
        S.save({"X_BEARER_TOKEN": "SUPERSECRET"})
        code, body, _ = self.call("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertNotIn(b"SUPERSECRET", body)
        self.assertTrue(json.loads(body)["platforms"]["x"]["ready"])
        S.save({"X_BEARER_TOKEN": ""})

    def test_credentials_roundtrip_via_api(self):
        code, body, _ = self.call("POST", "/api/credentials", {"YOUTUBE_API_KEY": "abc123"})
        self.assertEqual(code, 200)
        self.assertNotIn(b"abc123", body)
        self.assertEqual(S.get("YOUTUBE_API_KEY"), "abc123")
        self.call("POST", "/api/credentials", {"YOUTUBE_API_KEY": ""})

    def test_csrf_and_host_guards(self):
        self.assertEqual(self.call("POST", "/api/credentials", {"X_BEARER_TOKEN": "x"}, headers={"X-Coordwatch": "0"})[0], 403)
        self.assertEqual(self.call("POST", "/api/credentials", {}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/status", headers={"Host": "evil.example"})[0], 403)   # DNS-rebinding style

    def test_run_validation(self):
        self.assertEqual(self.call("POST", "/api/run", {"topic": "", "since": "2026-10-01", "until": "2026-10-02", "demo": True})[0], 400)
        self.assertEqual(self.call("POST", "/api/run", {"topic": "x", "since": "2026-10-05", "until": "2026-10-02", "demo": True})[0], 400)
        self.assertEqual(self.call("POST", "/api/run", {"topic": "x", "since": "2026-10-01", "until": "2026-10-02"})[0], 400)

    def _wait(self, jid, timeout=60):
        t = time.time()
        while time.time() - t < timeout:
            j = json.loads(self.call("GET", f"/api/jobs/{jid}")[1])
            if j["status"] in ("done", "error", "cancelled"):
                return j
            time.sleep(0.2)
        self.fail("job timed out")

    def test_demo_job_end_to_end_and_downloads(self):
        code, body, _ = self.call("POST", "/api/run", {"topic": "Acme Bank", "since": "2026-10-01", "until": "2026-10-14",
                                                         "demo": True, "discount_verified": True})
        self.assertEqual(code, 200)
        jid = json.loads(body)["id"]
        j = self._wait(jid)
        self.assertEqual(j["status"], "done", j)
        res = json.loads(self.call("GET", f"/api/jobs/{jid}/result")[1])
        self.assertEqual(res["meta"]["n_groups"], 2)
        code, html, h = self.call("GET", f"/api/jobs/{jid}/download/report.html")
        self.assertEqual(code, 200)
        self.assertIn(b"Acme Bank", html)
        self.assertEqual(self.call("GET", f"/api/jobs/{jid}/download/../../etc/passwd")[0], 404)

    def test_history_survives_a_restart(self):
        """A finished run is listed by /api/runs and can be reopened from disk once the in-memory job table is empty."""
        code, body, _ = self.call("POST", "/api/run", {"topic": "Acme Bank", "since": "2026-10-01", "until": "2026-10-14", "demo": True})
        jid = json.loads(body)["id"]
        self.assertEqual(self._wait(jid)["status"], "done")
        for _ in range(50):                                            # the meta file is written when the run is reported finished
            runs = json.loads(self.call("GET", "/api/runs")[1])["runs"]
            if any(r["id"] == jid for r in runs):
                break
            time.sleep(0.1)
        row = next(r for r in runs if r["id"] == jid)
        self.assertEqual(row["topic"], "Acme Bank")
        self.assertGreater(row["n_posts"], 100)
        self.assertEqual((row["since"], row["until"]), ("2026-10-01", "2026-10-14"))
        saved = dict(W.JOBS)
        W.JOBS.clear()                                                 # simulate a server restart
        try:
            res = json.loads(self.call("GET", f"/api/jobs/{jid}/result")[1])
            self.assertEqual(res["meta"]["topic"], "Acme Bank")
            self.assertEqual(self.call("GET", f"/api/jobs/{jid}/download/posts.csv")[0], 200)
            self.assertEqual(self.call("GET", "/api/jobs/zzzz/result")[0], 404)          # not hex: never touches the disk
            self.assertEqual(self.call("GET", "/api/jobs/..%2F..%2Fetc/result")[0], 404)
        finally:
            W.JOBS.update(saved)

    def test_search_endpoint_single_run_and_all_runs(self):
        jid = json.loads(self.call("POST", "/api/run", {"topic": "Acme Bank", "since": "2026-10-01", "until": "2026-10-14", "demo": True})[1])["id"]
        self.assertEqual(self._wait(jid)["status"], "done")
        for _ in range(50):
            if any(r["id"] == jid for r in json.loads(self.call("GET", "/api/runs")[1])["runs"]):
                break
            time.sleep(0.1)
        one = json.loads(self.call("GET", f"/api/search?job={jid}&q=most+liked+youtube+posts+about+savings")[1])
        self.assertTrue(one["posts"] and all(p["platform"] == "youtube" for p in one["posts"]))
        allr = json.loads(self.call("GET", "/api/search?job=all&q=savings")[1])
        self.assertTrue(any(r["run"]["id"] == jid for r in allr["runs"]))
        self.assertEqual(self.call("GET", "/api/search?job=all&q=")[0], 400)
        self.assertEqual(json.loads(self.call("GET", "/api/search?job=zzz&q=savings")[1])["posts"], [])

    def test_live_platform_without_keys_degrades_gracefully(self):
        def unconfigured():
            raise RuntimeError("no credentials")
        # hermetic: every route reports "not configured", so no network is touched (the free routes would otherwise go online)
        with mock.patch("coordwatch.collect._chain", return_value=[("api", unconfigured), ("free", unconfigured)]):
            jid = json.loads(self.call("POST", "/api/run", {"topic": "anything", "since": "2026-10-01", "until": "2026-10-02",
                                                             "platforms": ["youtube", "x"]})[1])["id"]
            j = self._wait(jid)
        self.assertEqual(j["status"], "error")
        self.assertIn("skipped", j["error"])          # tells the user *why* (missing keys), not a stack trace

    def test_failed_run_leaves_a_pasteable_log_without_secrets(self):
        def unconfigured():
            raise RuntimeError("no credentials")
        with mock.patch("coordwatch.collect._chain", return_value=[("api", unconfigured), ("free", unconfigured)]), \
                mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "SECRET-KEY-VALUE-123"}):
            jid = json.loads(self.call("POST", "/api/run", {"topic": "topg traders", "since": "2026-11-04", "until": "2026-11-08",
                                                             "platforms": ["youtube", "telegram"], "telegram_channels": "@abc"})[1])["id"]
            self._wait(jid)
            code, body, _ = self.call("GET", f"/api/jobs/{jid}/download/run_log.txt")
        txt = body.decode()
        self.assertEqual(code, 200)
        for needle in ("status      : ERROR", "topg traders", "2026-11-04", "youtube, telegram", "@abc", "not configured", "TIMELINE"):
            self.assertIn(needle, txt)
        self.assertNotIn("SECRET-KEY-VALUE-123", txt)          # credentials appear only as set / not set
        self.assertIn("YOUTUBE_API_KEY: set", txt)

    def test_logs_export_filters_by_date_range(self):
        from datetime import datetime, timedelta, timezone
        from urllib.parse import quote
        from coordwatch import secrets_store as S
        runs = S.home() / "runs"
        now = datetime.now(timezone.utc)
        for name, when, topic in (("aaaa01", now - timedelta(days=20), "OLD-RUN"), ("aaaa02", now - timedelta(days=1), "RECENT-RUN")):
            d = runs / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "run_log.txt").write_text(f"topic: {topic}\n", encoding="utf-8")
            (d / "run_meta.json").write_text(json.dumps({"id": name, "started": when.isoformat()}), encoding="utf-8")
        q = lambda a, b: f"from={quote((now - timedelta(days=a)).isoformat())}&to={quote((now - timedelta(days=b)).isoformat())}"
        code, body, _ = self.call("GET", "/api/logs?text=1&" + q(3, 0))
        j = json.loads(body)
        self.assertEqual(code, 200)
        self.assertIn("RECENT-RUN", j["text"])
        self.assertNotIn("OLD-RUN", j["text"])
        code, body, h = self.call("GET", "/api/logs?download=1&" + q(30, 0))
        self.assertIn("attachment", h.get("Content-Disposition", ""))
        self.assertTrue(body.decode().index("OLD-RUN") < body.decode().index("RECENT-RUN"))      # oldest first
        self.assertEqual(self.call("GET", "/api/logs?download=1&" + q(40, 30))[0], 404)         # nothing in range
        self.assertEqual(self.call("GET", "/api/logs?from=x&to=y")[0], 400)

    def test_abort_stops_a_running_job(self):
        from coordwatch.collectors.base import Cancelled
        started = threading.Event()

        def slow(*a, cancelled=None, log=None, **k):          # stands in for a long live collection
            log("fake: working…")
            started.set()
            for _ in range(200):
                if cancelled():
                    raise Cancelled()
                time.sleep(0.05)
            return [], []
        orig, W.collect_posts = W.collect_posts, slow
        try:
            jid = json.loads(self.call("POST", "/api/run", {"topic": "x", "since": "2026-10-01", "until": "2026-10-02", "demo": True})[1])["id"]
            self.assertTrue(started.wait(5))
            self.assertEqual(self.call("POST", f"/api/jobs/{jid}/cancel", {})[0], 200)
            j = self._wait(jid, 10)
            self.assertEqual(j["status"], "cancelled")
            self.assertTrue(any("abort" in l for l in j["log"]))
            self.assertIn("elapsed", j)
        finally:
            W.collect_posts = orig

    def test_upload_validates_and_feeds_a_run(self):
        row = [{"id": "1", "text": "Acme Bank scandal everywhere today wow", "createTimeISO": "2026-10-03T10:00:00Z",
                "authorMeta": {"name": "u1", "id": "9"}, "diggCount": 4}]
        code, body, _ = self.call("POST", "/api/upload?platform=tiktok&filename=t.json", raw=json.dumps(row).encode())
        self.assertEqual(code, 200, body)
        up = json.loads(body)
        self.assertEqual(up["posts"], 1)
        self.assertEqual(self.call("POST", "/api/upload?platform=tiktok&filename=evil.exe", raw=b"MZ")[0], 400)
        self.assertEqual(self.call("POST", "/api/upload?platform=tiktok&filename=a.json", raw=b"not json")[0], 400)
        jid = json.loads(self.call("POST", "/api/run", {"topic": "Acme Bank", "since": "2026-10-01", "until": "2026-10-05",
                                                         "upload_ids": [up["id"]]})[1])["id"]
        self.assertEqual(self._wait(jid)["status"], "done")


if __name__ == "__main__":
    unittest.main()


class CliSmokeTests(unittest.TestCase):
    def test_demo_run_via_cli_main(self):
        import tempfile
        from coordwatch.cli import main
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["run", "--topic", "Acme Bank", "--since", "2026-10-01", "--until", "2026-10-14",
                                   "--source", "demo", "--out", d]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "report.html")))
