"""X posts found through a free search engine (DuckDuckGo via `ddgs`): no X key, no login, no X account at risk.

Search engines index many public x.com/<handle>/status/<id> pages.  For each hit we keep the handle (from the URL), the text shown in the
result, and the exact post time, which is encoded in the tweet id itself (X ids are time-ordered "snowflakes").

Honest limits: only what the engine has indexed (a sample, not every post), the text is the engine's snippet (often shortened),
and there are no likes / shares / replies and no account profile data, so the coordination signals that need them stay silent for
these posts.  Treat the result as a sample of public X posts, and use the X API or browser-session route for full coverage."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import List, Optional

from ..filtering import matches_topic, topic_terms
from ..models import Post
from .base import Collector

_STATUS = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d{8,25})")
_EPOCH_MS = 1288834974657


def snowflake_time(tid: str) -> datetime:
    return datetime.fromtimestamp(((int(tid) >> 22) + _EPOCH_MS) / 1000, tz=timezone.utc)


def parse_hit(r: dict) -> Optional[dict]:
    url = r.get("href") or r.get("url") or ""
    m = _STATUS.match(url)
    if not m:
        return None
    text = " ".join(((r.get("body") or "") or (r.get("title") or "")).split())
    title = " ".join((r.get("title") or "").split())
    if not text:
        return None
    return {"handle": m.group(1), "id": m.group(2), "text": text, "title": title, "url": f"https://x.com/{m.group(1)}/status/{m.group(2)}"}


class XWeb(Collector):
    platform = "x"
    notes = ["X posts are a free, no-login sample of public posts: text may be shortened, with no likes/shares/replies "
             "and no account profile data. Use the X API or browser-session route for full coverage."]

    def __init__(self, backend=None, max_queries: int = 8, pause: float = 2.0):
        self.backend, self.max_queries, self.pause = backend, max_queries, pause

    def _backend(self):
        if self.backend is None:
            try:
                from ..discovery import DdgsBackend
                self.backend = DdgsBackend()
            except Exception as e:
                raise RuntimeError(f"free public-post lookup not available ({type(e).__name__}: pip install ddgs)")
        return self.backend

    def collect(self, topic: str, since: datetime, until: datetime, limit: int = 1000) -> List[Post]:
        be = self._backend()
        posts, seen = [], set()
        terms = topic_terms(topic) or [topic]
        queries = []
        for t in terms:
            q = t if t.startswith("#") or " " not in t else f'"{t}"'
            for site in ("x.com", "twitter.com"):
                queries.append(f"site:{site} inurl:status {q}")
        for q in queries[: self.max_queries]:
            self._check()
            self.log(f"x: looking for public posts ({q.split(' ',2)[-1]})…")
            try:
                rows = be.text(q, None, 50) or []
            except Exception as e:
                self.log(f"x: public-post lookup skipped ({type(e).__name__}: {str(e)[:100]})")
                continue
            kept = 0
            for r in rows:
                h = parse_hit(r)
                if not h or h["id"] in seen:
                    continue
                created = snowflake_time(h["id"])
                if created < since or created > until or not (matches_topic(h["text"], topic) or matches_topic(h["title"], topic)):
                    continue
                seen.add(h["id"])
                posts.append(Post(id=h["id"], platform="x", author_id=h["handle"], author_name=h["handle"], text=h["text"],
                                  created_at=created, url=h["url"]))
                kept += 1
            self.log(f"x: {len(rows)} found, {kept} kept for the window/topic ({len(posts)} total)")
            if len(posts) >= limit:
                break
            time.sleep(self.pause)
        return posts[:limit]
