import json
import os
import sys
import tempfile
import threading
import time
import unittest
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
            if j["status"] in ("done", "error"):
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

    def test_live_platform_without_keys_degrades_gracefully(self):
        jid = json.loads(self.call("POST", "/api/run", {"topic": "anything", "since": "2026-10-01", "until": "2026-10-02",
                                                         "platforms": ["youtube", "x"]})[1])["id"]
        j = self._wait(jid)
        self.assertEqual(j["status"], "error")
        self.assertIn("skipped", j["error"])          # tells the user *why* (missing keys), not a stack trace

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
