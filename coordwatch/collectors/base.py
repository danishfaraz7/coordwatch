"""Shared collector plumbing: polite HTTP client (throttle, retry, back-off, Retry-After, disk cache),
avatar perceptual hashing, and the Collector interface."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

from ..models import Post

log = logging.getLogger("coordwatch")


class PlatformBlocked(RuntimeError):
    """Raised on auth failures / bans / hard quota exhaustion - we never try to evade these."""


class Collector:
    platform = "?"
    #: human-readable limitations that are copied into the report ("collector_notes")
    notes: List[str] = []

    def collect(self, topic: str, since: datetime, until: datetime, limit: int = 1000) -> List[Post]:
        raise NotImplementedError


class HttpClient:
    """requests wrapper: min-interval throttle, exponential back-off with jitter on 429/5xx,
    honours Retry-After / x-rate-limit-reset, caches GETs on disk so reruns (and demos) cost no quota."""

    def __init__(self, min_interval: float = 1.0, max_retries: int = 5, cache_dir: Optional[str] = None,
                 session=None, sleep=time.sleep):
        if session is None:
            import requests  # lazy: not needed for demo/file mode
            session = requests.Session()
            session.headers["User-Agent"] = "coordwatch-research/0.1"
        self.s, self.min_interval, self.max_retries, self.sleep = session, min_interval, max_retries, sleep
        self.cache_dir = cache_dir
        self._last = 0.0
        self.stats = {"requests": 0, "retries": 0, "cache_hits": 0, "throttled_s": 0.0}
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, url, params, headers_key):
        h = hashlib.sha256(json.dumps([url, params, headers_key], sort_keys=True, default=str).encode()).hexdigest()
        return os.path.join(self.cache_dir, h + ".json")

    def get_json(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
        cp = None
        if self.cache_dir:
            cp = self._cache_path(url, params, sorted((headers or {}).keys()))
            if os.path.exists(cp):
                self.stats["cache_hits"] += 1
                with open(cp) as f:
                    return json.load(f)
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                self.stats["throttled_s"] += wait
                self.sleep(wait)
            self._last = time.time()
            self.stats["requests"] += 1
            r = self.s.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if cp:
                    with open(cp, "w") as f:
                        json.dump(data, f)
                return data
            if r.status_code in (401, 403):
                raise PlatformBlocked(f"{r.status_code} from {url}: credentials missing/invalid or access tier "
                                      f"too low. Not retrying or evading. Body: {r.text[:200]}")
            if r.status_code == 429 or r.status_code >= 500:
                delay = self._retry_delay(r, attempt)
                log.warning("HTTP %s from %s - sleeping %.1fs (attempt %d/%d)", r.status_code, url, delay,
                            attempt + 1, self.max_retries)
                self.stats["retries"] += 1
                self.sleep(delay)
                continue
            raise RuntimeError(f"HTTP {r.status_code} from {url}: {r.text[:200]}")
        raise PlatformBlocked(f"Gave up on {url} after {self.max_retries} retries (rate-limited). "
                              f"Partial results are kept; rerun later - the disk cache avoids repeating calls.")

    @staticmethod
    def _retry_delay(r, attempt: int) -> float:
        h = r.headers
        if h.get("Retry-After", "").isdigit():
            return min(float(h["Retry-After"]) + 1, 900)
        if h.get("x-rate-limit-reset", "").isdigit():                 # X API: epoch seconds
            return min(max(float(h["x-rate-limit-reset"]) - time.time(), 1) + 1, 900)
        return min(2 ** attempt + random.random(), 120)


# ------------------------------------------------------------------ avatar hashing
def dhash_bytes(data: bytes, size: int = 8) -> Optional[str]:
    """64-bit difference hash of an image (hex). Survives resizing/recompression, so a re-uploaded
    avatar on another account still matches. Returns None if Pillow is missing / image unreadable."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("L").resize((size + 1, size))
    except Exception:
        return None
    px = list(im.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (px[row * (size + 1) + col] > px[row * (size + 1) + col + 1])
    return f"{bits:016x}"


def avatar_hash_from_url(client: HttpClient, url: str, _memo: Dict[str, Optional[str]] = {}) -> Optional[str]:
    if not url:
        return None
    if url in _memo:
        return _memo[url]
    try:
        r = client.s.get(url, timeout=20)
        _memo[url] = dhash_bytes(r.content) if r.status_code == 200 else None
    except Exception:
        _memo[url] = None
    return _memo[url]
