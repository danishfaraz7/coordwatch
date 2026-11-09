"""YouTube via yt-dlp - no API key, no quota, free.  Used automatically when YOUTUBE_API_KEY is not set
(or when the official API is quota-blocked).

What you get: videos matching the topic (title + description, views, likes, comment count, upload time) and
top-level comments for each video (author channel id, text, time, likes, avatar URL -> perceptual hash).
Limits: channel creation date is not exposed (so the "accounts created together" signal is unavailable for YouTube
in this mode); each video costs one metadata fetch, so the number of videos is capped by the run depth."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

from ..filtering import topic_terms
from ..models import Post
import os
import re

from .base import Collector, HttpClient, PlatformBlocked, avatar_hash_from_url, log


_VIDEO_ID = re.compile(r"^[\w-]{11}$")                    # channel ids (UC...) and playlist ids (PL...) are longer
_BOT = ("confirm you", "not a bot", "sign in to")


class _Capture:
    """yt-dlp logger that stays quiet but remembers the last error, so a refusal (bot check) can be told apart from an
    ordinary 'video unavailable' (deleted/private/region-locked), which must not trip the fail-fast."""
    last = ""

    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): pass

    def error(self, m):
        self.last = str(m)


def _ts(e: dict) -> Optional[datetime]:
    ts = e.get("timestamp")
    if ts is None and e.get("upload_date"):
        try:
            return datetime.strptime(e["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else None


def map_video(e: dict) -> Optional[Post]:
    """yt-dlp info dict -> Post (pure function, unit-tested)."""
    t = _ts(e)
    if t is None or not e.get("id"):
        return None
    url = e.get("webpage_url") or f"https://www.youtube.com/watch?v={e['id']}"
    media = [{"type": "video", "url": url}]
    if e.get("thumbnail"):
        media.append({"type": "photo", "url": e["thumbnail"]})
    text = f'{e.get("title", "")}. {(e.get("description") or "")[:200]}'.strip()
    return Post(id=e["id"], platform="youtube", author_id=e.get("channel_id") or e.get("uploader_id") or "?",
                author_name=e.get("channel") or e.get("uploader") or "", text=text, created_at=t, url=url,
                likes=int(e.get("like_count") or 0), replies=int(e.get("comment_count") or 0),
                views=int(e["view_count"]) if e.get("view_count") is not None else None, media=media,
                author_followers=e.get("channel_follower_count"), author_verified=bool(e.get("channel_is_verified")))


def map_comment(c: dict, video_id: str) -> Optional[Post]:
    t = _ts(c)
    if t is None or not c.get("id") or not (c.get("text") or "").strip():
        return None
    return Post(id=c["id"], platform="youtube", author_id=c.get("author_id") or c.get("author") or "?",
                author_name=(c.get("author") or "").lstrip("@"), text=c["text"], created_at=t,
                url=f"https://www.youtube.com/watch?v={video_id}&lc={c['id']}", likes=int(c.get("like_count") or 0),
                reply_to=video_id if c.get("parent") in (None, "root") else c.get("parent"),
                author_verified=bool(c.get("author_is_verified")))


class YtDlpYouTube(Collector):
    platform = "youtube"
    notes = ["YouTube (yt-dlp, no API key): channel creation dates are not exposed, so the 'accounts created together' "
             "signal is unavailable here; only the top comments of each video are read."]

    def __init__(self, max_videos: int = 30, max_comments: int = 100, hash_avatars: bool = True, max_avatars: int = 80):
        self.max_videos, self.max_comments = max_videos, max_comments
        self.hash_avatars, self.max_avatars = hash_avatars, max_avatars

    def collect(self, topic: str, since: datetime, until: datetime, limit: int = 1000) -> List[Post]:
        import yt_dlp  # lazy: only needed for live YouTube without a key
        cap = _Capture()
        base = {"quiet": True, "no_warnings": True, "logger": cap, "skip_download": True, "ignoreerrors": True, "retries": 3,
                "extractor_retries": 3, "sleep_interval_requests": 1, "socket_timeout": 20}
        if os.environ.get("YTDLP_COOKIES_FILE"):                # optional: cookies of a throwaway Google account
            base["cookiefile"] = os.environ["YTDLP_COOKIES_FILE"]
        ids: List[str] = []
        terms = topic_terms(topic, combined=True)[:4]
        # newest-first search: current yt-dlp has no `ytsearchdate` prefix, so use the search-results URL with YouTube's
        # "upload date" sort (sp=CAI%3D); plain relevance search (`ytsearchN:`) is the fallback if that returns nothing.
        with yt_dlp.YoutubeDL({**base, "extract_flat": "in_playlist", "playlistend": self.max_videos}) as ydl:
            for t in terms:
                self._check()
                for q in (f"https://www.youtube.com/results?search_query={quote_plus(t)}&sp=CAI%253D", f"ytsearch{self.max_videos}:{t}"):
                    try:
                        res = ydl.extract_info(q, download=False) or {}
                    except Exception as e:
                        log.debug("yt-dlp search %s: %s", q, e)
                        res = {}
                    new = [e["id"] for e in res.get("entries", []) if e and _VIDEO_ID.match(e.get("id") or "") and e["id"] not in ids]
                    if new:
                        ids += new
                        break
        if not ids:
            raise RuntimeError("yt-dlp search returned nothing (offline, blocked by YouTube, or no matches)")
        self.log(f"youtube (yt-dlp): {len(ids)} candidate videos")
        opts = {**base, "getcomments": True,
                "extractor_args": {"youtube": {"max_comments": [str(self.max_comments), "all", "0", "0"], "comment_sort": ["top"]}}} \
            if self.max_comments else base
        posts: List[Post] = []
        avatar_urls: dict = {}
        failures = 0                                            # consecutive videos YouTube refused to serve
        with yt_dlp.YoutubeDL(opts) as ydl:
            for n, vid in enumerate(ids[: self.max_videos * len(terms)], 1):
                self._check()
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                if not info:
                    if any(k in cap.last.lower() for k in _BOT):    # a refusal, not just an unavailable video
                        failures += 1
                    cap.last = ""
                    if failures >= 3 and not posts:
                        raise PlatformBlocked(
                            "YouTube refused video requests from this IP (bot check / sign-in wall - typical on cloud and datacentre "
                            "addresses). Not retrying or evading. Use a free YOUTUBE_API_KEY, run from a home connection, or set "
                            "YTDLP_COOKIES_FILE to a cookie export of a throwaway Google account.")
                    continue
                failures = 0
                v = map_video(info)
                if v and since <= v.created_at <= until:
                    posts.append(v)
                for c in info.get("comments") or []:
                    cp = map_comment(c, vid)
                    if cp and since <= cp.created_at <= until:
                        posts.append(cp)
                        if c.get("author_thumbnail"):
                            avatar_urls[cp.author_id] = c["author_thumbnail"]
                if n % 5 == 0:
                    self.log(f"youtube (yt-dlp): {n}/{len(ids)} videos read, {len(posts)} posts")
                if len(posts) >= limit:
                    break
        if self.hash_avatars and avatar_urls:
            client = HttpClient(min_interval=0.2)
            hashes = {}
            for uid, url in list(avatar_urls.items())[: self.max_avatars]:
                hashes[uid] = avatar_hash_from_url(client, url)
            for p in posts:
                p.avatar_hash = hashes.get(p.author_id)
        log.info("yt-dlp: %d posts from %d videos", len(posts), len(ids))
        return posts[:limit]
