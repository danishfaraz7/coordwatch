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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .. import __version__
from .. import activity, naming
from .. import ai
from .. import runlog
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
DOWNLOADS = {"executive_report.pdf": "application/pdf", "results.json": "application/json", "posts.csv": "text/csv", "narratives.csv": "text/csv",
             "volume_by_platform.csv": "text/csv", "coordinated_groups.csv": "text/csv", "origins.csv": "text/csv",
             "cross_platform.csv": "text/csv", "daily_counts.csv": "text/csv", "term_mentions.csv": "text/csv", "narrative_by_day.csv": "text/csv",
             "narrative_by_term.csv": "text/csv", "overview.json": "application/json", "plain_summary.txt": "text/plain; charset=utf-8", "cross_platform_summary.txt": "text/plain; charset=utf-8",
             "report.html": "text/html; charset=utf-8", "run_log.txt": "text/plain; charset=utf-8"}
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
        self.started = datetime.now(timezone.utc)
        self.notes: list = []
        self.log_written = False      # the run log is written after the status flips; clients must not see 'finished' before it exists
        self.cancel = threading.Event()

    def log(self, msg: str):
        self.logs.append(f"{time.time() - self.t0:5.1f}s  {msg}")


JOBS: Dict[str, Job] = {}
UPLOADS: Dict[str, dict] = {}
LOCK = threading.Lock()


def _day(v):
    """YYYY-MM-DD for a date or datetime (the run meta must stay JSON-friendly)."""
    return str(v)[:10] if v else None


def _write_run_log(job: Job):
    """Always leave a pasteable run log next to the outputs - on success, failure and abort alike."""
    try:
        job.dir.mkdir(parents=True, exist_ok=True)
        (job.dir / "run_log.txt").write_text(
            runlog.build(job.params, job.status, job.error, job.logs, job.result, job.started, datetime.now(timezone.utc), job.notes),
            encoding="utf-8")
        activity.record("run", run=job.id, status=job.status, topic=job.params.get("topic"), platforms=job.params.get("platforms"),
                        posts=(job.result or {}).get("meta", {}).get("n_posts"), error=job.error)
        started = job.started or datetime.now(timezone.utc)
        meta = {"id": job.id, "started": started.astimezone(timezone.utc).isoformat(), "topic": job.params.get("topic"),
                "platforms": job.params.get("platforms"), "since": _day(job.params.get("since")), "until": _day(job.params.get("until")),
                "status": job.status}
        if job.result:
            m = job.result["meta"]
            meta.update(n_posts=m.get("n_posts"), n_accounts=m.get("n_accounts"), n_narratives=m.get("n_narratives"), n_groups=m.get("n_groups"))
        (job.dir / "run_meta.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
    except Exception:
        traceback.print_exc()
    finally:
        job.log_written = True


def run_dir(run_id: str):
    """Folder of a finished run on disk (survives restarts), or None. run_id is hex only, so it cannot escape the runs folder."""
    if not re.fullmatch(r"[a-f0-9]+", run_id or ""):
        return None
    d = S.home() / "runs" / run_id
    return d if d.is_dir() else None


def list_runs(limit: int = 30) -> list:
    """Finished runs that left a results file, newest first (for the Recent investigations list)."""
    runs = S.home() / "runs"
    out = []
    for d in (runs.iterdir() if runs.is_dir() else []):
        if not (d / "results.json").is_file():
            continue
        try:
            m = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({k: m.get(k) for k in ("id", "started", "topic", "platforms", "since", "until", "n_posts", "n_accounts", "n_narratives", "n_groups")})
    out.sort(key=lambda r: r.get("started") or "", reverse=True)
    return out[:limit]


def collect_logs(start: datetime, end: datetime) -> tuple:
    """Concatenate the secret-free run logs of every run that started inside [start, end]. Returns (text, count)."""
    runs = S.home() / "runs"
    found = []
    for d in (runs.iterdir() if runs.is_dir() else []):
        log = d / "run_log.txt"
        if not log.is_file():
            continue
        try:
            when = parse_dt(json.loads((d / "run_meta.json").read_text(encoding="utf-8"))["started"])
        except Exception:
            when = datetime.fromtimestamp(log.stat().st_mtime, timezone.utc)   # runs from before run_meta existed
        if when and start <= when <= end:
            found.append((when, log))
    found.sort(key=lambda x: x[0])
    sep = "\n\n" + "=" * 78 + "\n\n"
    blocks = [p.read_text(encoding="utf-8", errors="replace") for _, p in found]
    act, n_act = activity.collect(start, end)
    if act:
        blocks.append(act)
    return sep.join(blocks), len(found) + (1 if n_act else 0)


def run_job(job: Job):
    p = job.params
    job.status = "running"
    try:
        _run_job(job, p)
    finally:
        _write_run_log(job)


def _run_job(job: Job, p: dict):
    try:
        files = [(UPLOADS[u]["path"], UPLOADS[u]["platform"]) for u in p["upload_ids"] if u in UPLOADS]
        posts, notes = collect_posts(p["topic"], p["since"], p["until"], p["platforms"], use_demo=p["demo"], files=files,
                                     telegram_channels=p["telegram_channels"], limit=p["limit"], depth=p["depth"],
                                     cancelled=job.cancel.is_set, log=job.log, notes_out=job.notes)
        if job.cancel.is_set():
            raise Cancelled()
        job.log(f"{len(posts)} posts collected - analysing…")
        cfg = Config(discount_verified=p["discount_verified"])
        result = analyse(posts, p["topic"], p["since"], p["until"], None, cfg, notes, topic_filter=False)
        job.log(f"{result['meta']['n_narratives']} narratives, {result['meta']['n_groups']} coordinated group(s)")
        if p.get("ai_names"):
            try:
                acfg = ai.current_config()
                if not acfg["ready"]:
                    job.log("AI story names skipped: no AI provider is configured (Settings)")
                else:
                    job.log(f"naming stories with AI ({acfg['label']})…")
                    k = naming.name_stories(result, acfg)
                    job.log(f"AI named {k} stor{'y' if k == 1 else 'ies'}" if k else "AI story names: the model did not return usable titles; keeping keyword labels")
                    activity.record("ai_names", run_id=job.id, named=k, provider=acfg["provider"])
            except Exception as ex:
                job.log(f"AI story names skipped ({type(ex).__name__}: {str(ex)[:120]}); keeping keyword labels")
        export_all(result, str(job.dir))
        (job.dir / "report.html").write_text(render(result), encoding="utf-8")
        job.result, job.status = result, "done"
    except Cancelled:
        job.status, job.error = "cancelled", "Aborted by user."
        job.log("aborted by user")
    except SystemExit as e:                      # analyse() raises this when nothing matched
        job.status = "error"
        job.error = NO_MATCH if "No posts matched" in (str(e) or "No posts matched") else str(e)
        why = [l.split("  ", 1)[-1] for l in job.logs if "skipped" in l or "blocked" in l][:2]      # missing keys / blocked platform: worth saying
        if why:
            job.error += "\nNote: " + " | ".join(why)
    except Exception as e:
        traceback.print_exc()
        job.error, job.status = f"{type(e).__name__}: {e}", "error"


NO_MATCH = ("No matches found for this search. Try another keyword, hashtag, person, brand or event, or widen the date range.\n"
            "Examples:  \"Acme Bank\"   \"#AcmeBankCollapse\"   \"Jensen Huang\"   \"IPL auction\"   \"Tata Motors\"\n"
            "Tip: hashtags work best on Telegram; the 'See what's trending' button suggests topics people are searching right now.")


def _hint(job: Job) -> str:
    bad = [l for l in job.logs if "skipped" in l or "blocked" in l or "failed" in l or "matched the topic" in l or "no readable" in l]
    return ("Details: " + " | ".join(l.split('  ', 1)[-1] for l in bad[:3])) if bad else ""


def platform_status() -> dict:
    st = S.status()
    return {
        "version": __version__,
        "platforms": {
            # every live platform has a free route, so it is usable without paid credentials (see collect._chain)
            "x": {"mode": "live", "ready": bool(st["X_BEARER_TOKEN"]["set"] or st["X_COOKIES_FILE"]["set"]), "needs": ["X_BEARER_TOKEN"],
                  "route": "X API" if st["X_BEARER_TOKEN"]["set"] else "browser session (free, experimental)" if st["X_COOKIES_FILE"]["set"] else ""},
            "youtube": {"mode": "live", "ready": True, "needs": ["YOUTUBE_API_KEY"],
                        "route": "YouTube Data API" if st["YOUTUBE_API_KEY"]["set"] else "yt-dlp (no key)"},
            "telegram": {"mode": "live", "ready": True, "needs": ["TELEGRAM_API_ID", "TELEGRAM_API_HASH"], "login_done": S.telegram_logged_in(),
                         "route": "Telegram API" if (st["TELEGRAM_API_ID"]["set"] and st["TELEGRAM_API_HASH"]["set"] and S.telegram_logged_in())
                         else "public web preview (no login)"},
            **{p: {"mode": "file", "ready": True, "needs": []} for p in FILE_ONLY},
        },
        "credentials": st,
        "ai": {k: v for k, v in ai.current_config().items() if k != "key"},
        "ai_presets": {k: {"label": p["label"], "base": p.get("base", ""), "needs_key": p["needs_key"], "hint": p["hint"]} for k, p in ai.PRESETS.items()},
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
            "depth": body.get("depth") if body.get("depth") in ("quick", "standard", "deep") else "standard", "discount_verified": bool(body.get("discount_verified")), "ai_names": bool(body.get("ai_names"))}


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

    def _result_for(self, job_id: str):
        j = JOBS.get(job_id)
        if j and j.result:
            return j.result
        d = run_dir(job_id) if re.fullmatch(r"[a-f0-9]+", job_id or "") else None
        if d and (d / "results.json").is_file():
            return json.loads((d / "results.json").read_text(encoding="utf-8"))
        return None

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
        if path == "/api/trending":
            q = parse_qs(urlparse(self.path).query)
            try:
                from ..trending import trending
                a, b = parse_dt(q["since"][0]), parse_dt(q["until"][0])
                if not a or not b or a > b:
                    raise ValueError
            except Exception:
                return self._json(400, {"error": "choose a valid start and end date"})
            chans = [c for c in re.split(r"[,\s]+", (q.get("channels") or [""])[0]) if c]
            out = trending(a, b, (q.get("geo") or ["IN"])[0], chans)
            activity.record("trending", since=str(a)[:10], until=str(b)[:10], geo=(q.get("geo") or ["IN"])[0], channels=chans or None,
                            sources={x.get("id") or x.get("name"): (len(x.get("items") or x.get("terms") or []), x.get("error") or x.get("note"))
                                     for x in out.get("sources", []) if isinstance(x, dict)})
            return self._json(200, out)
        if path == "/api/runs":
            return self._json(200, {"runs": list_runs()})
        if path == "/api/logs":
            q = parse_qs(urlparse(self.path).query)
            try:
                a, b = parse_dt(q["from"][0]), parse_dt(q["to"][0])
                if not a or not b or a > b:
                    raise ValueError
            except Exception:
                return self._json(400, {"error": "choose a valid from/to range"})
            text, n = collect_logs(a, b)
            if q.get("download"):
                if not n:
                    return self._json(404, {"error": "no runs in that range"})
                return self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8", {"Content-Disposition": 'attachment; filename="coordwatch_logs.txt"'})
            return self._json(200, {"count": n, "text": text if q.get("text") else None})
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j:
                return self._json(404, {"error": "unknown job"})
            shown = j.status if (j.log_written or j.status in ("queued", "running")) else "running"
            return self._json(200, {"id": j.id, "status": shown, "log": j.logs, "error": j.error, "elapsed": round(time.time() - j.t0, 1),
                                    "summary": j.result["meta"] if j.result else None})
        if path == "/api/search":
            q = parse_qs(urlparse(self.path).query)
            text = (q.get("q") or [""])[0].strip()[:300]
            if not text:
                return self._json(400, {"error": "type something to search for"})
            from ..search import search
            job_id = (q.get("job") or [""])[0]
            if job_id != "all":
                out = search(self._result_for(job_id) or {}, text)
                activity.record("search", scope="this run", run=job_id, query=text, understood=out.get("understood"), filters=out.get("filters"),
                                posts=len(out.get("posts") or []), total_posts=out.get("total_posts"),
                                stories=len(out.get("narratives") or []), groups=len(out.get("groups") or []))
                return self._json(200, out)
            hits = []                                                       # application-wide: every saved run, newest first
            for r in list_runs()[:15]:
                res = self._result_for(r["id"])
                if res:
                    out = search(res, text, limit=5)
                    if out["posts"] or out["groups"] or out["narratives"]:
                        hits.append({"run": {k: r.get(k) for k in ("id", "topic", "since", "until", "n_posts")}, "understood": out["understood"], "total_posts": out["total_posts"],
                                     "posts": out["posts"], "narratives": out["narratives"], "groups": out["groups"]})
            activity.record("search", scope="all runs", query=text, runs_with_hits=len(hits),
                            posts=sum(len(h["posts"]) for h in hits), stories=sum(len(h["narratives"]) for h in hits), groups=sum(len(h["groups"]) for h in hits))
            return self._json(200, {"query": text, "runs": hits})
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/result", path)
        if m:
            j = JOBS.get(m.group(1))
            if j and j.result:
                return self._json(200, j.result)
            d = run_dir(m.group(1))                        # a run from an earlier session
            if d and (d / "results.json").is_file():
                return self._send(200, (d / "results.json").read_bytes(), "application/json")
            return self._json(404, {"error": "no result"})
        m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/download/([\w.]+)", path)
        if m and m.group(2) in DOWNLOADS:
            j = JOBS.get(m.group(1))
            d = j.dir if j else run_dir(m.group(1))
            f = d / m.group(2) if d else None
            if m.group(2) == "executive_report.pdf" and f and not f.exists() and (d / "results.json").is_file():
                from ..pdfreport import available, build as build_pdf        # older run, or reportlab was installed later: make it now
                if not available():
                    return self._json(501, {"error": "The PDF needs the free reportlab package. Run: pip install reportlab  (then restart the app and try again)."})
                build_pdf(json.loads((d / "results.json").read_text(encoding="utf-8")), str(f))
            if f and f.exists():
                activity.record("download", run=m.group(1), file=m.group(2))
                disp = "inline" if m.group(2) == "report.html" else f'attachment; filename="{m.group(2)}"'
                return self._send(200, f.read_bytes(), DOWNLOADS[m.group(2)], {"Content-Disposition": disp})
        self._json(404, {"error": "not found"})

    def _build_report(self, job_id: str, body: dict):
        """Report for the stories the person picked (one, several or all), optionally with ONE AI summary of exactly those stories."""
        from ..subset import subset
        from ..report import render
        res = self._result_for(job_id)
        if not res:
            return self._json(404, {"error": "No finished run to build a report from."})
        stories = body.get("stories", "all")
        fmt = body.get("format", "html")
        if fmt not in ("html", "pdf"):
            raise ValueError("Choose a web page or a PDF.")
        try:
            sub = res if stories == "all" else subset(res, [int(x) for x in stories])
        except (TypeError, ValueError) as e:
            raise ValueError(str(e) or "Pick at least one story.")
        sel = sub["meta"].get("selection")
        ai_block = None
        t0 = time.time()
        if body.get("ai"):
            names = ", ".join(f"Story {n['id']}" for n in sub["narratives"] if n["id"] >= 0)
            q = ("Write ONE short summary (at most 6 plain sentences, very simple words) covering all of these stories together (" + names +
                 "): what people are saying, how they connect, which platform and account started them, and whether any accounts seem to act together. "
                 "Say that coordination is a clue, not proof. Cite sources like [1].")
            try:
                if not ai.current_config()["ready"]:
                    S.save({"AI_PROVIDER": "pollinations", "AI_MODEL": "", "AI_BASE_URL": ""})
                cfg = ai.current_config()
                srcs = ai.build_sources(sub)
                text, model = ai.answer(q, ai.build_context(sub), cfg)
                ai_block = {"text": re.sub(r"\bnarrative\s*#\s*(\d+)", r"Story \1", re.sub(r"</?data>", "", text)).strip(), "model": model, "sources": ai.cited(text, srcs)}
            except (ai.AIError, Exception) as e:       # the report is still produced; the reason is written into it
                ai_block = {"error": str(e)[:300]}
        activity.record("report", run=job_id, stories=(sel or {}).get("stories", "all"), format=fmt, ai=bool(body.get("ai")),
                        ai_ok=bool(ai_block and not ai_block.get("error")) if body.get("ai") else None, ai_error=(ai_block or {}).get("error"), seconds=round(time.time() - t0, 1),
                        summary=(ai_block or {}).get("text"))
        tag = "all-stories" if not sel else "stories-" + "-".join(str(i) for i in sel["stories"][:6])
        if fmt == "pdf":
            from ..pdfreport import available, build as build_pdf
            if not available():
                return self._json(501, {"error": "The PDF needs the free reportlab package. Run: pip install reportlab  (then restart the app and try again)."})
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                f = Path(d) / "r.pdf"
                build_pdf(sub, str(f), ai_block)
                data = f.read_bytes()
            return self._send(200, data, "application/pdf", {"Content-Disposition": f'attachment; filename="report_{tag}.pdf"'})
        return self._send(200, render(sub, ai=ai_block).encode("utf-8"), "text/html; charset=utf-8", {"Content-Disposition": f'inline; filename="report_{tag}.html"'})

    def do_POST(self):
        if not self._guard(True):
            return
        url = urlparse(self.path)
        try:
            if url.path == "/api/credentials":
                body = json.loads(self._body(50_000) or b"{}")
                S.save({k: v for k, v in body.items() if isinstance(v, (str, type(None)))})
                activity.record("settings", changed=sorted(k for k, v in body.items() if isinstance(v, (str, type(None)))))   # names only, never values
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
                activity.record("abort", run=j.id)
                return self._json(200, {"ok": True})
            if url.path == "/api/validate":
                body = json.loads(self._body(2_000) or b"{}")
                if body.get("service") not in ("youtube", "gemini", "ai", "x", "telegram"):
                    raise ValueError("Unknown service.")
                res = V.validate(body["service"])
                activity.record("validate", service=body["service"], result=str(res.get("message") or res.get("ok") or res)[:200] if isinstance(res, dict) else None)
                return self._json(200, res)
            if url.path == "/api/ask":
                body = json.loads(self._body(20_000) or b"{}")
                if not body.get("ai"):
                    raise ValueError("AI answers are off. Tick the AI box to send a summary of this run to Gemini.")
                job = JOBS.get(str(body.get("job_id", "")))
                if not job or not job.result:
                    raise ValueError("No finished run to ask about.")
                cfg = ai.current_config()
                if not cfg["ready"]:
                    raise ValueError("Set up an AI provider in ⚙ Settings first.")
                question = str(body.get("question", "")).strip()
                if not question:
                    raise ValueError("Type a question.")
                ctx = ai.build_context(job.result)
                t0 = time.time()
                try:
                    text, model = ai.answer(question, ctx, cfg)
                except ai.AIError as e:
                    activity.record("ai", run=job.id, question=question, provider=cfg.get("provider"), ok=False, error=str(e),
                                    seconds=round(time.time() - t0, 1), context_chars=len(str(ctx)))
                    return self._json(502, {"error": str(e)})
                activity.record("ai", run=job.id, question=question, provider=cfg.get("provider"), model=model, ok=True,
                                seconds=round(time.time() - t0, 1), context_chars=len(str(ctx)), answer_chars=len(text), answer=text)
                refs = ai.cited(text, ai.build_sources(job.result))
                return self._json(200, {"answer": text, "model": model, "sources": refs})
            m = re.fullmatch(r"/api/jobs/([a-f0-9]+)/report", url.path)
            if m:
                return self._build_report(m.group(1), json.loads(self._body(20_000) or b"{}"))
            if url.path == "/api/run":
                params = parse_run(json.loads(self._body(100_000) or b"{}"))
                job = Job(params)
                with LOCK:
                    JOBS[job.id] = job
                activity.record("run-start", run=job.id, topic=params.get("topic"), platforms=params.get("platforms"),
                                since=_day(params.get("since")), until=_day(params.get("until")), demo=params.get("demo") or None)
                threading.Thread(target=run_job, args=(job,), daemon=True).start()
                return self._json(200, {"id": job.id})
        except (ValueError, json.JSONDecodeError) as e:
            if url.path == "/api/ask":
                activity.record("ai", ok=False, error=str(e), stage="refused before sending")
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
