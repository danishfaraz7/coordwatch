import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["COORDWATCH_HOME"] = tempfile.mkdtemp()
for k in ("GEMINI_API_KEY", "AI_API_KEY", "AI_PROVIDER", "AI_BASE_URL", "AI_MODEL", "YOUTUBE_API_KEY"):
    os.environ.pop(k, None)
from coordwatch import ai, secrets_store as S, validate as V
from coordwatch.web import server as W

ai.MIN_INTERVAL = 0
ai.BACKOFF = (0, 0)


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body if body is not None else {}

    def json(self):
        return self._b


def chat_ok(text):
    return R(200, {"choices": [{"message": {"content": text}}]})


class ProviderTests(unittest.TestCase):
    def tearDown(self):
        S.save({k: "" for k in S.KEYS})

    def test_config_resolution(self):
        c0 = ai.current_config()                                    # nothing configured -> the free no-login service is used by default
        self.assertEqual((c0["provider"], c0["ready"]), ("pollinations", True))
        S.save({"AI_PROVIDER": "groq", "AI_API_KEY": "gk"})
        c = ai.current_config()
        self.assertEqual((c["provider"], c["base"], c["ready"], c["local"]), ("groq", "https://api.groq.com/openai/v1", True, False))
        S.save({"AI_PROVIDER": "ollama", "AI_API_KEY": ""})
        c = ai.current_config()
        self.assertTrue(c["ready"] and c["local"])                  # local model needs no key
        S.save({"AI_PROVIDER": "custom", "AI_BASE_URL": "", "AI_API_KEY": "k"})
        self.assertFalse(ai.current_config()["ready"])              # custom needs a URL
        S.save({"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "g"})
        self.assertTrue(ai.current_config()["ready"])

    def test_base_url_must_be_https_or_localhost(self):
        for ok in ("https://api.groq.com/openai/v1", "http://localhost:11434/v1", "http://127.0.0.1:1234/v1/"):
            ai.check_base_url(ok)
        for bad in ("http://evil.example/v1", "ftp://x/v1", "file:///etc/passwd", "javascript:alert(1)", "", "https://"):
            with self.assertRaises(ai.AIError):
                ai.check_base_url(bad)

    def test_request_shape_bearer_header_and_untrusted_data_prompt(self):
        seen = {}

        def post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, hdr=headers, body=json)
            return chat_ok("hello")
        cfg = {"provider": "groq", "base": "https://api.groq.com/openai/v1", "key": "SECRET", "model": "llama-x", "local": False}
        self.assertEqual(ai.ask_openai(cfg, "who?", "{}", post=post), ("hello", "llama-x"))
        self.assertEqual(seen["url"], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(seen["hdr"]["Authorization"], "Bearer SECRET")
        self.assertNotIn("SECRET", seen["url"])
        self.assertIn("never as instructions", seen["body"]["messages"][0]["content"])
        self.assertIn("<data>", seen["body"]["messages"][1]["content"])
        self.assertNotIn("tools", seen["body"])

    def test_think_tags_stripped_and_no_auth_header_without_key(self):
        seen = {}

        def post(url, headers=None, json=None, timeout=None):
            seen["hdr"] = headers
            return chat_ok("<think>secret chain of thought</think>\nFinal answer.")
        cfg = {"provider": "ollama", "base": "http://localhost:11434/v1", "key": None, "model": "qwen3", "local": True}
        text, _ = ai.ask_openai(cfg, "q", "{}", post=post)
        self.assertEqual(text, "Final answer.")
        self.assertNotIn("Authorization", seen["hdr"])

    def test_model_auto_pick_uses_models_endpoint(self):
        ids = ["whisper-large-v3", "llama-guard-4", "llama-3.3-70b-versatile", "qwen/qwen3-32b", "text-embedding-3"]
        self.assertEqual(ai.pick_openai_model(ids, "groq"), "qwen/qwen3-32b")
        self.assertEqual(ai.pick_openai_model(["a/b", "qwen/qwen3-235b:free", "qwen/qwen3-14b"], "openrouter"), "qwen/qwen3-235b:free")
        calls = []

        def get(url, headers=None, timeout=None):
            calls.append(url)
            return R(200, {"data": [{"id": "llama-3.3-70b-versatile"}]})
        cfg = {"provider": "groq", "base": "https://api.groq.com/openai/v1", "key": "k", "model": "", "local": False}
        text, model = ai.ask_openai(cfg, "q", "{}", post=lambda *a, **k: chat_ok("x"), get=get)
        self.assertEqual(model, "llama-3.3-70b-versatile")
        self.assertTrue(calls[0].endswith("/models"))

    def test_errors_retries_and_messages(self):
        cfg = {"provider": "groq", "base": "https://api.groq.com/openai/v1", "key": "k", "model": "m", "local": False}
        n = {"c": 0}

        def flaky(*a, **k):
            n["c"] += 1
            return R(503) if n["c"] < 3 else chat_ok("finally")
        self.assertEqual(ai.ask_openai(cfg, "q", "{}", post=flaky, sleep=lambda s: None)[0], "finally")
        for code, needle in ((401, "rejected"), (404, "not found"), (429, "rate limit"), (503, "busy")):
            with self.assertRaises(ai.AIError) as cm:
                ai.ask_openai(cfg, "q", "{}", post=lambda *a, **k: R(code), sleep=lambda s: None)
            self.assertIn(needle, str(cm.exception).lower())

        class ReadTimeout(Exception):
            pass
        with self.assertRaises(ai.AIError) as cm:
            ai.ask_openai(cfg, "q", "{}", post=lambda *a, **k: (_ for _ in ()).throw(ReadTimeout("t")), sleep=lambda s: None)
        self.assertIsInstance(cm.exception, ai.RetryAfter)

    def test_validate_ai_states_and_model_list(self):
        S.save({"AI_PROVIDER": "gemini", "GEMINI_API_KEY": ""})
        self.assertEqual(V.validate("ai")["state"], "unset")
        S.save({"AI_PROVIDER": "groq", "AI_API_KEY": "k"})
        r = V.validate("ai", get=lambda *a, **k: R(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}]}))
        self.assertEqual(r["state"], "connected")
        self.assertIn("llama-3.3-70b-versatile", r["models"])
        self.assertIn("Groq", r["message"])
        self.assertEqual(V.validate("ai", get=lambda *a, **k: R(401))["state"], "invalid")
        self.assertEqual(V.validate("ai", get=lambda *a, **k: R(429))["state"], "limited")
        S.save({"AI_MODEL": "not-there"})
        self.assertEqual(V.validate("ai", get=lambda *a, **k: R(200, {"data": [{"id": "x"}]}))["state"], "limited")
        S.save({"AI_PROVIDER": "custom", "AI_BASE_URL": "http://evil.example/v1", "AI_API_KEY": "k", "AI_MODEL": ""})
        self.assertNotEqual(V.validate("ai", get=lambda *a, **k: R(200, {"data": []}))["state"], "connected")   # refuses plain-http remote

    def test_status_exposes_plain_settings_but_never_keys(self):
        S.save({"AI_PROVIDER": "openrouter", "AI_API_KEY": "TOPSECRET", "AI_MODEL": "qwen/x:free"})
        st = W.platform_status()
        blob = json.dumps(st)
        self.assertNotIn("TOPSECRET", blob)
        self.assertEqual(st["credentials"]["AI_MODEL"]["value"], "qwen/x:free")
        self.assertEqual(st["ai"]["provider"], "openrouter")
        self.assertNotIn("key", st["ai"])
        self.assertIn("groq", st["ai_presets"])


class AskWithProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        W.Handler.allow_hosts = []
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        from coordwatch.collectors import demo
        from coordwatch.config import Config
        from coordwatch.pipeline import analyse
        from datetime import datetime, timezone
        res = analyse(demo.generate(42)[0], "Acme Bank", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 14, 23, tzinfo=timezone.utc), None, Config())
        job = W.Job({})
        job.result, job.status = res, "done"
        W.JOBS[job.id] = job
        cls.jid = job.id

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_port}{path}", data=json.dumps(body).encode(), method="POST", headers={"X-Coordwatch": "1"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_local_provider_without_key_is_dispatched(self):
        S.save({"AI_PROVIDER": "ollama", "AI_MODEL": "qwen3"})
        orig = ai.ask_openai
        try:
            ai.ask_openai = lambda cfg, q, ctx, **k: (f"via {cfg['provider']}/{cfg['model']}", cfg["model"])
            code, body = self.post("/api/ask", {"ai": True, "job_id": self.jid, "question": "hi"})
            self.assertEqual((code, body["answer"]), (200, "via ollama/qwen3"))
        finally:
            ai.ask_openai = orig
            S.save({k: "" for k in S.KEYS})

    def test_unconfigured_is_a_clean_400(self):
        S.save({k: "" for k in S.KEYS}); S.save({"AI_PROVIDER": "gemini"})
        self.assertEqual(self.post("/api/ask", {"ai": True, "job_id": self.jid, "question": "hi"})[0], 400)

    def test_validate_endpoint_accepts_ai(self):
        S.save({k: "" for k in S.KEYS}); S.save({"AI_PROVIDER": "gemini"})
        code, body = self.post("/api/validate", {"service": "ai"})
        self.assertEqual((code, body["state"]), (200, "unset"))


if __name__ == "__main__":
    unittest.main()


class AutoRetryTests(unittest.TestCase):
    def test_answer_retrying_waits_out_the_cooldown_and_reports_each_second(self):
        calls, waits, slept = [], [], []
        orig = ai.answer

        def fake(q, c, cfg=None, **kw):
            calls.append(1)
            if len(calls) < 3:
                raise ai.RetryAfter(4)
            return "ok", "m"
        ai.answer = fake
        try:
            out = ai.answer_retrying("q", "{}", {}, on_wait=lambda left, a, n: waits.append((left, a)), sleep=slept.append)
        finally:
            ai.answer = orig
        self.assertEqual(out, ("ok", "m"))
        self.assertEqual(len(calls), 3)
        self.assertEqual(waits[:4], [(4, 1), (3, 1), (2, 1), (1, 1)])      # a visible countdown, per attempt
        self.assertEqual(len(slept), 8)

    def test_gives_up_after_the_last_attempt(self):
        orig = ai.answer
        ai.answer = lambda *a, **k: (_ for _ in ()).throw(ai.RetryAfter(3))
        try:
            with self.assertRaises(ai.AIError):
                ai.answer_retrying("q", "{}", {}, attempts=2, sleep=lambda s: None)
        finally:
            ai.answer = orig
