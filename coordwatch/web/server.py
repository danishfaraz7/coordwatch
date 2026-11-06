"""Zero-dependency web server for coordwatch (stdlib http.server).

Security model (this tool stores API keys and runs collectors, so it is local-first):
  * binds 127.0.0.1 by default; accepts only localhost / *.app.github.dev / --allow-host Host headers (anti DNS-rebinding)
  * every POST needs the X-Coordwatch header and a same-origin Origin (anti cross-site request)
  * credential values are write-only: the API never returns them
  * strict CSP, no inline scripts; uploads are extension-checked, size-capped and parsed, never executed
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .. import __version__
from .. import ai
from .. import validate as V
from .. import secrets_store as S
from ..collectors.base import Cancelled
from ..collect import ALL_PLATFORMS, FILE_ONLY, LIVE, collect_posts
from ..config import Config
from ..export import export_all
from ..models import parse_dt
from ..pipeline import analyse
from ..report import render

STATIC = Path(__file__).parent / "static"
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/app.css": ("app.css", "text/css; charset=utf-8")}
DOWNLOADS = {"results.json": "application/json", "posts.csv": "text/csv", "narratives.csv": "text/csv",
             "volume_by_platform.csv": "text/csv", "coordinated_groups.csv": "text/csv", "origins.csv": "text/csv",
             "report.html": "text/html; charset=utf-8"}
MAX_UPLOAD = 60 * 1024 * 1024
CSP = ("default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class Job:
    def __init__(self, params: dict):
        self.id = uuid.uuid4().hex[:12]
        self.params, self.status, self.logs, self.error = params, "queued", [], None
        self.result: Optional[dict] = None
        self.dir = S.home() / "runs" / self.id
        self.t0 = time.time()
        self.cancel = threading.Event()

    def log(self, msg: str):
        self.logs.append(f"{time.time() - self.t0:5.1f}s  {msg}")


JOBS: Dict[str, Job] = {}
UPLOADS: Dict[str, dict] = {}
LOCK = threading.Lock()


def run_job(job: Job):
    p = job.params
    job.status = "running"
    try:
        files = [(UPLOADS[u]["path"], UPLOADS[u]["platform"]) for u in p["upload_ids"] if u in UPLOADS]
        posts, notes = collect_posts(p["topic"], p["since"], p["until"], p["platforms"], use_demo=p["demo"], files=files,
                                     telegram_channels=p["telegram_channels"], limit=p["limit"], depth=p["depth"],
                                     cancelled=job.cancel.is_set, log=job.log)
        if job.cancel.is_set():
            raise Cancelled()
        job.log(f"{len(posts)} posts collected - analysing…")
        cfg = Config(discount_verified=p["discount_verified"])
        result = analyse(posts, p["topic"], p["since"], p["until"], None, cfg, notes, topic_filter=False)
        job.log(f"{result['meta']['n_narratives']} narratives, {result['meta']['n_groups']} coordinated group(s)")
        export_all(result, str(job.dir))
        (job.dir / "report.html").write_text(render(result), encoding="utf-8")
        job.result, job.status = result, "done"
    except Cancelled:
        job.status, job.error = "cancelled", "Aborted by user."
        job.log("aborted by user")
    except SystemExit as e:                      # analyse() raises this when nothing matched
        job.error, job.status = str(e) or "No posts matched.", "error"
        if notes_hint := _hint(job):
            job.error += " " + notes_hint
    except Exception as e:
        traceback.print_exc()
        job.error, job.status = f"{type(e).__name__}: {e}", "error"


def _hint(job: Job) -> str:
    bad = [l for l in job.logs if "skipped" in l or "blocked" in l or "failed" in l]
    return ("Details: " + " | ".join(l.split('  ', 1)[-1] for l in bad[:3])) if bad else ""


def platform_status() -> dict:
    st = S.status()
    return {
        "version": __version__,
        "platforms": {
            "x": {"mode": "live", "ready": st["X_BEARER_TOKEN"]["set"], "needs": ["X_BEARER_TOKEN"]},
            "youtube": {"mode": "live", "ready": st["YOUTUBE_API_KEY"]["set"], "needs": ["YOUTUBE_API_KEY"]},
            "telegram": {"mode": "live", "ready": st["TELEGRAM_API_ID"]["set"] and st["TELEGRAM_API_HASH"]["set"] and S.telegram_logged_in(),
                         "needs": ["TELEGRAM_API_ID", "TELEGRAM_API_HASH"], "login_done": S.telegram_logged_in()},
            **{p: {"mode": "file", "ready": True, "needs": []} for p in FILE_ONLY},
        },
        "credentials": st,
        "in_codespaces": bool(os.environ.get("CODESPACES")),
    }


def parse_run(body: dict) -> dict:
    topic = str(body.get("topic", "")).strip()
    if not topic or len(topic) > 200:
        raise ValueError("Enter a topic (max 200 characters).")
    since, until = parse_dt(body.get("since")), parse_dt(body.get("until"))
    if not since or not until or until < since:
        raise ValueError("Pick a valid date range.")
    until = until.replace(hour=23, minute=59, second=59)
    plats = [p for p in body.get("platforms", []) if p in ALL_PLATFORMS]
    ups = [u for u in body.get("upload_ids", []) if u in UPLOADS]
    demo = bool(body.get("demo"))
    if not (plats or ups or demo):
        raise ValueError("Select at least one platform, import a file, or use the demo data.")
    return {"topic": topic, "since": since.astimezone(timezone.utc), "until": until.astimezone(timezone.utc),
            "platforms": plats, "upload_ids": ups, "demo": demo, "telegram_channels": str(body.get("telegram_channels", ""))[:500],
            "limit": max(50, min(int(body.get("limit") or 500), 5000)),
            "depth": body.get("depth") if body.get("depth") in ("quick", "standard", "deep") else "standard", "discount_verified": bool(body.get("discount_verified"))}


class Handler(BaseHTTPRequestHandler):
    server_version = "coordwatch"
    allow_hosts: List[str] = []

    def log_message(self, *a):
        pass

    # ---------------------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def _guard(self, post: bool) -> bool:
        host = self.headers.get("Host", "")
        name = host.rsplit(":", 1)[0].strip("[]").lower() if not host.startswith("[") else host.split("]")[0].strip("[")
        ok = (name in ("localhost", "127.0.0.1", "::1") or name.endswith(".app.github.dev") or host in self.allow_hosts
              or name in self.allow_hosts)
        if not ok:
            self._json(403, {"error": "Host not allowed. Use http://localhost:PORT (or --allow-host)."})
            return False
        if post:
            origin = self.headers.get("Origin")
            if self.headers.get("X-Coordwatch") != "1" or (origin and urlparse(origin).netloc != host):
                self._json(403, {"error": "Cross-site request blocked."})
                return False
        return True

    def _body(self, limit: int) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError(f"Body too large (limit {limit // (1024 * 1024)} MB).")
        return self.rfile.read(n)

    # ---------------------------------------------------------------- routes
    def do_GET(self):
        if not self._guard(False):
            return
        path = urlparse(self.path).path
        if path in STATIC_FILES:
            fn, ct = STATIC_FILES[path]
            return self._send(200, (STATIC / fn).read_bytes(), ct)
        if path == "/api/status":
            return self._json(200, platform_status())
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j:
                return self._json(404, {"error": "unknown job"})
            return self._json(200, {"id": j.id, "status": j.status, "log": j.logs, "error": j.error, "elapsed": round(time.time() - j.t0, 1),
                                    "summary": j.result["meta"] if j.result else None})
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/result", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j or not j.result:
                return self._json(404, {"error": "no result"})
            return self._json(200, j.result)
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/download/([\w.]+)", path)
        if m and m.group(2) in DOWNLOADS and m.group(1) in JOBS:
            f = JOBS[m.group(1)].dir / m.group(2)
            if f.exists():
                disp = "inline" if m.group(2) == "report.html" else f'attachment; filename="{m.group(2)}"'
                return self._send(200, f.read_bytes(), DOWNLOADS[m.group(2)], {"Content-Disposition": disp})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard(True):
            return
        url = urlparse(self.path)
        try:
            if url.path == "/api/credentials":
                body = json.loads(self._body(50_000) or b"{}")
                S.save({k: v for k, v in body.items() if isinstance(v, (str, type(None)))})
                return self._json(200, platform_status())
            if url.path == "/api/upload":
                q = parse_qs(url.query)
                plat = (q.get("platform", [""])[0] or "").lower()
                name = os.path.basename(q.get("filename", ["upload"])[0])
                if plat not in ALL_PLATFORMS:
                    raise ValueError("Unknown platform for upload.")
                if not name.lower().endswith((".json", ".jsonl", ".ndjson", ".csv")):
                    raise ValueError("Upload a .json, .jsonl or .csv export.")
                data = self._body(MAX_UPLOAD)
                uid = uuid.uuid4().hex[:12]
                d = S.home() / "uploads"
                d.mkdir(exist_ok=True)
                path = d / f"{uid}{Path(name).suffix.lower()}"
                path.write_bytes(data)
                from ..collectors.fileimport import load_file
                try:
                    n = len(load_file(str(path), plat))
                except Exception as e:
                    path.unlink(missing_ok=True)
                    raise ValueError(f"Could not read that file: {type(e).__name__}: {e}")
                if n == 0:
                    path.unlink(missing_ok=True)
                    raise ValueError("No usable posts found (need text + a date column/field).")
                UPLOADS[uid] = {"path": str(path), "platform": plat, "filename": name, "posts": n}
                return self._json(200, {"id": uid, "platform": plat, "filename": name, "posts": n})
            m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/cancel", url.path)
            if m:
                j = JOBS.get(m.group(1))
                if not j:
                    return self._json(404, {"error": "unknown job"})
                j.cancel.set()
                j.log("abort requested - stopping after the current request…")
                return self._json(200, {"ok": True})
            if url.path == "/api/validate":
                body = json.loads(self._body(2_000) or b"{}")
                if body.get("service") not in ("youtube", "gemini", "x", "telegram"):
                    raise ValueError("Unknown service.")
                return self._json(200, V.validate(body["service"]))
            if url.path == "/api/ask":
                body = json.loads(self._body(20_000) or b"{}")
                if not body.get("ai"):
                    raise ValueError("AI answers are off. Tick the AI box to send a summary of this run to Gemini.")
                job = JOBS.get(str(body.get("job_id", "")))
                if not job or not job.result:
                    raise ValueError("No finished run to ask about.")
                key = S.get("GEMINI_API_KEY")
                if not key:
                    raise ValueError("Add a Gemini API key in ⚙ Settings first.")
                question = str(body.get("question", "")).strip()
                if not question:
                    raise ValueError("Type a question.")
                try:
                    text, model = ai.ask(key, question, ai.build_context(job.result))
                except ai.AIError as e:
                    return self._json(502, {"error": str(e)})
                return self._json(200, {"answer": text, "model": model})
            if url.path == "/api/run":
                params = parse_run(json.loads(self._body(100_000) or b"{}"))
                job = Job(params)
                with LOCK:
                    JOBS[job.id] = job
                threading.Thread(target=run_job, args=(job,), daemon=True).start()
                return self._json(200, {"id": job.id})
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"error": str(e)})
        self._json(404, {"error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8000, allow_hosts: Optional[List[str]] = None) -> int:
    Handler.allow_hosts = [h.lower() for h in (allow_hosts or [])]
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"coordwatch web app  ->  http://localhost:{srv.server_port}   (Ctrl+C to stop)")
    if host not in ("127.0.0.1", "localhost"):
        print("NOTE: listening on all interfaces; only Hosts localhost / *.app.github.dev / --allow-host are accepted.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0
