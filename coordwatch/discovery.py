"""Discovery stage: use a free search engine (DuckDuckGo via `ddgs`, no key) as a poor man's Google.

For the topic it runs `site:` queries per platform plus a news query, then
  * extracts Telegram channels from t.me links  -> fed to the Telegram collector when you gave none
  * lists YouTube video ids and other-platform links as "web mentions" (link + title + snippet only)
  * finds the earliest *dated* web mention (news results carry dates) to compare with the first social post

Honest limits: roughly 10-30 results per query, coarse engine-side date filter (day/week/month/year), snippets only,
unofficial scraping of a search engine (can be rate-limited -> retried with back-off, reported per query, never fatal),
not exhaustive.  Web mentions carry no account or engagement data, so they never enter coordination detection."""
from __future__ import annotations

import json
import logging
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from .filtering import matches_topic
from .models import parse_dt

log = logging.getLogger("coordwatch.discovery")

SITES = ["t.me", "youtube.com", "x.com", "facebook.com", "instagram.com", "tiktok.com"]
DOMAIN_PLATFORM = {"t.me": "telegram", "telegram.me": "telegram", "youtube.com": "youtube", "youtu.be": "youtube",
                   "x.com": "x", "twitter.com": "x", "facebook.com": "facebook", "fb.com": "facebook",
                   "instagram.com": "instagram", "tiktok.com": "tiktok", "reddit.com": "reddit"}
TG_RESERVED = {"joinchat", "addstickers", "share", "c", "iv", "proxy", "socks", "addemoji", "setlanguage", "login",
               "bg", "addtheme", "boost", "s", "media", "giftcode"}
_tg = re.compile(r"^https?://(?:www\.)?(?:t|telegram)\.me/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})(?:/\d+)?(?:[/?#].*)?$")
_yt = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/)|youtu\.be/)([\w-]{11})")


class DdgsBackend:
    """DuckDuckGo through the free `ddgs` package (no API key, no account)."""

    def __init__(self):
        from ddgs import DDGS
        self._d = DDGS(timeout=20)

    ENGINES = ("auto", "bing", "brave", "yahoo", "mojeek")

    def text(self, query, timelimit, max_results):
        """Try several free search engines in turn and return the first that has results (one engine being blocked or empty is common)."""
        last = None
        for eng in self.ENGINES:
            try:
                rows = self._d.text(query, timelimit=timelimit, max_results=max_results, backend=eng)
                if rows:
                    return rows
            except Exception as e:      # blocked / no results / network: try the next engine
                last = e
        if last:
            raise last
        return []

    def news(self, query, timelimit, max_results):
        return self._d.news(query, timelimit=timelimit if timelimit in ("d", "w", "m") else None, max_results=max_results)


class GoogleCseBackend:
    """Google's official Programmable Search JSON API (free: 100 queries a day).  Needs an API key and a search-engine id (cx) set to
    search x.com (and twitter.com) - see the README.  Returns rows shaped like DdgsBackend's: href, title, body."""

    def __init__(self, key: str, cx: str, session=None):
        self.key, self.cx = key, cx
        import urllib.request  # noqa: F401  (stdlib only)

    def text(self, query, timelimit, max_results):
        import json
        import urllib.error
        import urllib.parse
        import urllib.request
        rows = []
        for start in range(1, max(1, min(max_results, 30)) + 1, 10):          # 10 results per call; 3 calls = 30 results
            params = {"key": self.key, "cx": self.cx, "q": query, "start": start, "num": 10}
            if timelimit in ("d", "w", "m", "y"):
                params["dateRestrict"] = timelimit + "1" if timelimit != "w" else "w1"
            try:
                with urllib.request.urlopen("https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params), timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (400, 403, 429) and rows:
                    break
                raise RuntimeError(f"Google search API HTTP {e.code} (check the key, the search engine id and the daily 100-query limit)")
            items = data.get("items") or []
            for it in items:
                rows.append({"href": it.get("link", ""), "title": it.get("title", ""), "body": it.get("snippet", "")})
            if len(items) < 10:
                break
        return rows


def timelimit_for(start: datetime, now: Optional[datetime] = None) -> Optional[str]:
    days = ((now or datetime.now(timezone.utc)) - start).days
    return "d" if days <= 1 else "w" if days <= 7 else "m" if days <= 31 else "y" if days <= 366 else None


def classify(url: str) -> str:
    m = re.match(r"^https?://(?:www\.|m\.|mobile\.)?([^/:?#]+)", url or "")
    if not m:
        return "web"
    host = m.group(1).lower()
    for dom, plat in DOMAIN_PLATFORM.items():
        if host == dom or host.endswith("." + dom):
            return plat
    return "web"


def telegram_channel(url: str) -> Optional[str]:
    m = _tg.match(url or "")
    return None if not m or m.group(1).lower() in TG_RESERVED else m.group(1)


def youtube_id(url: str) -> Optional[str]:
    m = _yt.search(url or "")
    return m.group(1) if m else None


def build_queries(topic: str) -> List[Tuple[str, str]]:
    t = topic.strip().replace(" OR ", " | ")
    quoted = f'"{t.lstrip("#")}"' if " " in t.lstrip("#") and "|" not in t else t
    return [(f"site:{d}", f"site:{d} {quoted}") for d in SITES] + [("news", quoted)]


def _is_empty(e: Exception) -> bool:
    """ddgs raises DDGSException('No results found.') for an empty result set - that is an answer, not a failure."""
    return "no results" in str(e).lower()


def _search(fn, q: str, tl: Optional[str], n: int, sleep=None) -> Tuple[list, Optional[str]]:
    """-> (rows, error).  Empty is not an error and is never retried.  The engine-side date filter is coarse and often
    empties niche queries, so an empty result is retried ONCE without it (exact date filtering happens afterwards).
    Real errors (rate limit, timeout) get two short back-off retries."""
    last_err = None
    for use_tl in ([tl, None] if tl else [None]):
        for attempt in range(3):
            try:
                rows = fn(q, use_tl, n)
                if rows:
                    return rows, None
                break                                            # empty: try the next (unfiltered) variant
            except Exception as e:
                if _is_empty(e):
                    break
                last_err = f"{type(e).__name__}: {str(e)[:160]}"
                if attempt < 2:
                    (sleep or time.sleep)(3 * (attempt + 1) + random.random())
                else:
                    return [], last_err
    return [], last_err


def _normalise(r: dict, kind: str, query: str) -> Optional[dict]:
    url = r.get("href") or r.get("url") or ""
    if not url:
        return None
    dt = None
    if r.get("date"):
        try:
            dt = parse_dt(r["date"]).isoformat()
        except Exception:
            dt = None
    return {"url": url, "title": (r.get("title") or "").strip(), "snippet": (r.get("body") or "").strip(),
            "platform": classify(url), "source": r.get("source", ""), "date": dt, "kind": kind, "query": query}


def discover(topic: str, start: datetime, end: datetime, out_dir: str, backend=None, max_results: int = 20,
             pause: Tuple[float, float] = (2.5, 5.0), budget_s: float = 90.0) -> dict:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cache = Path(out_dir) / "discovery.json"
    tl, qlog, results, seen = timelimit_for(start), [], [], set()
    try:
        backend = backend or DdgsBackend()
    except Exception as e:
        return _finish(topic, [], [{"query": "(init)", "ok": False, "error": f"{type(e).__name__}: {e} - pip install ddgs"}], start, end, cache)
    queries = build_queries(topic)
    t_start = time.time()
    for i, (kind, q) in enumerate(queries):
        if time.time() - t_start > budget_s:                     # discovery is a convenience, never a reason to stall a run
            qlog.append({"query": q, "ok": False, "error": f"skipped: discovery time budget ({budget_s:.0f}s) used up", "seconds": 0})
            continue
        t0 = time.time()
        fn = backend.news if kind == "news" else backend.text
        rows, err = _search(fn, q, tl, max_results)
        new = 0
        for r in rows:
            n = _normalise(r, kind, q)
            if n and n["url"] not in seen:
                seen.add(n["url"])
                results.append(n)
                new += 1
        entry = {"query": q, "ok": err is None, "n_results": len(rows), "n_new": new, "seconds": round(time.time() - t0, 1)}
        if err:
            entry["error"] = err
        qlog.append(entry)
        if i < len(queries) - 1:
            time.sleep(random.uniform(*pause))
    return _finish(topic, results, qlog, start, end, cache)


def _finish(topic, results, qlog, start, end, cache: Path) -> dict:
    # Only trust a channel if the search result that pointed at it actually mentions the topic (title/snippet/url).  Without
    # this, a short or ambiguous topic (e.g. "NFP") collects any t.me link the engine returns - police, casinos, ...
    rel = [r for r in results if matches_topic(f"{r['title']} {r['snippet']} {r['url']}", topic)]
    chan = Counter(c for r in rel if (c := telegram_channel(r["url"])))
    unrelated = sorted({c for r in results if r not in rel and (c := telegram_channel(r["url"])) and c not in chan})
    dated = sorted((r for r in results if r["date"] and start <= parse_dt(r["date"]) <= end), key=lambda r: r["date"])
    out = {"topic": topic, "queries": qlog, "n_results": len(results), "results": results,
           "telegram_channels": [{"channel": c, "hits": n} for c, n in chan.most_common()],
           "telegram_channels_unrelated": unrelated,          # linked by the engine but never mention the topic: NOT used
           "youtube_video_ids": sorted({y for r in results if (y := youtube_id(r["url"]))}),
           "dated_mentions": dated, "earliest_dated_mention": dated[0] if dated else None,
           "by_platform": dict(Counter(r["platform"] for r in results))}
    cache.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
