"""YouTube Data API v3 collector (official API, API key). Videos matching the topic + their comments.
Quota: search.list = 100 units/call, everything else 1 unit; default 10,000 units/day -> we cap pages.
Not exercised against the live API in the repo's tests (no key in CI) - parsers are unit-tested on
recorded-shape payloads."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

from ..models import Post, parse_dt
from .base import Collector, HttpClient, avatar_hash_from_url

API = "https://www.googleapis.com/youtube/v3"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_comment(item: dict, video_id: str, channels: Dict[str, dict]) -> Post:
    top = item["snippet"]["topLevelComment"]
    sn = top["snippet"]
    ch_id = (sn.get("authorChannelId") or {}).get("value", sn.get("authorDisplayName", "?"))
    ch = channels.get(ch_id, {})
    return Post(
        id=top["id"], platform="youtube", author_id=ch_id, author_name=sn.get("authorDisplayName", ""),
        text=sn.get("textOriginal") or sn.get("textDisplay", ""), created_at=parse_dt(sn["publishedAt"]),
        url=f"https://www.youtube.com/watch?v={video_id}&lc={top['id']}", likes=int(sn.get("likeCount", 0)),
        replies=int(item["snippet"].get("totalReplyCount", 0)), reply_to=video_id,
        author_created=parse_dt(ch.get("publishedAt")), avatar_hash=ch.get("avatar_hash"))


def parse_video(item: dict, channels: Dict[str, dict]) -> Post:
    sn, st = item["snippet"], item.get("statistics", {})
    ch = channels.get(sn["channelId"], {})
    return Post(
        id=item["id"] if isinstance(item["id"], str) else item["id"]["videoId"], platform="youtube",
        author_id=sn["channelId"], author_name=sn.get("channelTitle", ""),
        text=f"{sn.get('title', '')}. {(sn.get('description', '') or '')[:200]}".strip(), created_at=parse_dt(sn["publishedAt"]),
        url=f"https://www.youtube.com/watch?v={item['id'] if isinstance(item['id'], str) else item['id']['videoId']}",
        likes=int(st.get("likeCount", 0)), replies=int(st.get("commentCount", 0)), views=int(st.get("viewCount", 0)),
        media=[{"type": "video", "url": f"https://www.youtube.com/watch?v={item['id'] if isinstance(item['id'], str) else item['id']['videoId']}"},
               {"type": "photo", "url": (sn.get("thumbnails", {}).get("high") or {}).get("url", "")}],
        author_created=parse_dt(ch.get("publishedAt")), avatar_hash=ch.get("avatar_hash"))


class YouTubeCollector(Collector):
    platform = "youtube"
    notes = ["YouTube: official Data API v3; search.list costs 100 quota units so at most `max_videos` videos are "
             "searched; comments are top-level only; comment search is limited to the sampled videos."]

    def __init__(self, api_key: str = None, client: HttpClient = None, max_videos: int = 40, max_comments: int = 300,
                 hash_avatars: bool = True):
        self.key = api_key or os.environ.get("YOUTUBE_API_KEY")
        if not self.key:
            raise RuntimeError("Set YOUTUBE_API_KEY (Google Cloud console -> YouTube Data API v3).")
        self.c = client or HttpClient(min_interval=0.3, cache_dir=".cache/youtube")
        self.max_videos, self.max_comments, self.hash_avatars = max_videos, max_comments, hash_avatars

    def _channels(self, ids: List[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        ids = sorted(set(ids))
        for i in range(0, len(ids), 50):
            d = self.c.get_json(f"{API}/channels", {"part": "snippet", "id": ",".join(ids[i:i + 50]), "key": self.key})
            for it in d.get("items", []):
                sn = it["snippet"]
                thumb = (sn.get("thumbnails", {}).get("default") or {}).get("url")
                out[it["id"]] = {"publishedAt": sn.get("publishedAt"),
                                 "avatar_hash": avatar_hash_from_url(self.c, thumb) if self.hash_avatars else None}
        return out

    def collect(self, topic, since, until, limit=1000):
        from datetime import datetime, timedelta, timezone
        # the API rejects a publishedAfter/Before in the future (400 invalid argument) - and "today" in the user's
        # timezone can still be tomorrow in UTC - so never look past "now"
        until = min(until, datetime.now(timezone.utc) - timedelta(seconds=30))
        vids = []
        # search.list returns newest-first, so one query only ever reaches the last few hours.
        # Slice the range into day windows (max 14) and take the top videos of each.
        days = max(1, min(14, (until - since).days + 1))
        per_window = max(3, self.max_videos // days)
        for d in range(days):
            w0 = since + timedelta(days=d)
            w1 = min(until, w0 + timedelta(days=1))
            if w1 <= w0:
                continue
            p = {"part": "snippet", "q": topic, "type": "video", "maxResults": min(50, per_window), "order": "relevance",
                 "publishedAfter": _iso(w0), "publishedBefore": _iso(w1), "key": self.key}
            d_ = self.c.get_json(f"{API}/search", p)
            vids += [it["id"]["videoId"] for it in d_.get("items", [])]
        vids = vids[:self.max_videos]
        stats = {}
        for i in range(0, len(vids), 50):
            d = self.c.get_json(f"{API}/videos", {"part": "snippet,statistics", "id": ",".join(vids[i:i + 50]), "key": self.key})
            stats.update({it["id"]: it for it in d.get("items", [])})
        comments_raw = []
        for v in vids:
            token, got = None, 0
            while got < self.max_comments:
                p = {"part": "snippet", "videoId": v, "maxResults": 100, "order": "time", "textFormat": "plainText", "key": self.key}
                if token:
                    p["pageToken"] = token
                try:
                    d = self.c.get_json(f"{API}/commentThreads", p)
                except Exception as e:      # comments disabled on a video -> 403 is expected, skip it
                    from .base import PlatformBlocked
                    if isinstance(e, PlatformBlocked):
                        break
                    raise
                for it in d.get("items", []):
                    comments_raw.append((v, it)); got += 1
                token = d.get("nextPageToken")
                if not token:
                    break
        ch_ids = [s["snippet"]["channelId"] for s in stats.values()] + \
                 [(it["snippet"]["topLevelComment"]["snippet"].get("authorChannelId") or {}).get("value", "") for _, it in comments_raw]
        channels = self._channels([c for c in ch_ids if c])
        posts = [parse_video(s, channels) for s in stats.values()]
        posts += [parse_comment(it, v, channels) for v, it in comments_raw]
        return [p for p in posts if since <= p.created_at <= until][:limit]
