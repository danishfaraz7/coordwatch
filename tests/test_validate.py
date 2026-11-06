import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["COORDWATCH_HOME"] = tempfile.mkdtemp()
for k in ("X_BEARER_TOKEN", "YOUTUBE_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "GEMINI_API_KEY"):
    os.environ.pop(k, None)
from coordwatch import secrets_store as S
from coordwatch import validate as V


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}

    def json(self):
        return self._b


class ValidateTests(unittest.TestCase):
    def tearDown(self):
        S.save({k: "" for k in S.KEYS})

    def test_unset_when_no_key(self):
        for s in ("youtube", "gemini", "x", "telegram"):
            self.assertEqual(V.validate(s, get=lambda *a, **k: R(200))["state"], "unset")

    def test_youtube_states(self):
        S.save({"YOUTUBE_API_KEY": "KEY123"})
        self.assertEqual(V.validate("youtube", get=lambda *a, **k: R(200))["state"], "connected")
        self.assertEqual(V.validate("youtube", get=lambda *a, **k: R(400, {"error": {"errors": [{"reason": "keyInvalid"}]}}))["state"], "invalid")
        self.assertEqual(V.validate("youtube", get=lambda *a, **k: R(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}))["state"], "limited")
        self.assertEqual(V.validate("youtube", get=lambda *a, **k: R(403, {"error": {"errors": [{"reason": "accessNotConfigured"}]}}))["state"], "limited")

    def test_gemini_states_and_model_name(self):
        S.save({"GEMINI_API_KEY": "G"})
        ok = R(200, {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}]})
        r = V.validate("gemini", get=lambda *a, **k: ok)
        self.assertEqual(r["state"], "connected")
        self.assertIn("gemini-2.5-flash", r["message"])
        self.assertEqual(V.validate("gemini", get=lambda *a, **k: R(429))["state"], "limited")
        self.assertEqual(V.validate("gemini", get=lambda *a, **k: R(400))["state"], "invalid")

    def test_x_states(self):
        S.save({"X_BEARER_TOKEN": "T"})
        self.assertEqual(V.validate("x", get=lambda *a, **k: R(200))["state"], "connected")
        self.assertEqual(V.validate("x", get=lambda *a, **k: R(401))["state"], "invalid")
        self.assertEqual(V.validate("x", get=lambda *a, **k: R(402))["state"], "limited")

    def test_telegram_needs_login_session(self):
        S.save({"TELEGRAM_API_ID": "1", "TELEGRAM_API_HASH": "h"})
        self.assertEqual(V.validate("telegram")["state"], "limited")

    def test_network_errors_never_leak_the_key(self):
        S.save({"YOUTUBE_API_KEY": "SECRETKEY"})

        def boom(*a, **k):
            raise ConnectionError("https://x/?key=SECRETKEY failed")
        r = V.validate("youtube", get=boom)
        self.assertEqual(r["state"], "unreachable")
        self.assertNotIn("SECRETKEY", str(r))


if __name__ == "__main__":
    unittest.main()
