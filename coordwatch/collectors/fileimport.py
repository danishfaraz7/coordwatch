"""Import JSON / JSONL / CSV exports. This is the route for platforms with no usable public API
(TikTok, Instagram, Facebook, Snapchat): export from an Apify actor / Bright Data / your own lawful
collection and map the fields here.  Field aliases cover the common scraper schemas."""
from __future__ import annotations

import csv
import json
from typing import Any, Dict, List, Optional

from ..models import Post, parse_dt

ALIASES = {
    "id": ["id", "post_id", "tweet_id", "message_id", "pk", "shortCode", "video_id"],
    "text": ["text", "full_text", "caption", "message", "content", "desc", "description", "body", "title"],
    "created_at": ["created_at", "date", "timestamp", "createTimeISO", "createTime", "taken_at", "publishedAt",
                   "time", "posted_at", "datetime"],
    "author_id": ["author_id", "user_id", "authorMeta.id", "owner.id", "ownerId", "channel_id", "author.id"],
    "author_name": ["author_name", "username", "author", "ownerUsername", "authorMeta.name", "owner.username",
                    "channel", "user.screen_name", "author.userName"],
    "likes": ["likes", "like_count", "likesCount", "diggCount", "favorite_count", "reactions"],
    "shares": ["shares", "retweet_count", "shareCount", "forwards", "reposts"],
    "replies": ["replies", "reply_count", "commentCount", "commentsCount", "comments"],
    "views": ["views", "view_count", "playCount", "videoViewCount", "videoPlayCount"],
    "url": ["url", "link", "postUrl", "webVideoUrl", "permalink"],
    "author_created": ["author_created", "user.created_at", "authorMeta.createTime", "account_created"],
    "author_followers": ["author_followers", "followers", "user.followers_count", "authorMeta.fans"],
    "avatar_hash": ["avatar_hash", "profile_image_hash"],
    "reshare_of": ["reshare_of", "retweeted_status.id", "forwarded_from_message_id"],
    "reshare_of_author": ["reshare_of_author", "retweeted_status.user.id", "forwarded_from"],
}


def _get(d: Dict[str, Any], path: str):
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _pick(d: dict, field: str):
    for a in ALIASES.get(field, [field]):
        v = _get(d, a) if "." in a else d.get(a)
        if v not in (None, ""):
            return v
    return None


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _media(d: dict) -> list:
    out = []
    m = d.get("media") or d.get("images") or d.get("mediaUrls") or d.get("photos") or []
    if isinstance(m, str):
        m = [x for x in m.split("|") if x]
    for it in m if isinstance(m, list) else []:
        if isinstance(it, str):
            out.append({"type": "video" if it.split("?")[0].endswith((".mp4", ".mov", ".webm")) else "photo", "url": it})
        elif isinstance(it, dict):
            out.append({"type": it.get("type", "photo"), "url": it.get("url") or it.get("src", "")})
    for key in ("videoUrl", "video_url", "videoMeta.downloadAddr"):
        v = _get(d, key) if "." in key else d.get(key)
        if v:
            out.append({"type": "video", "url": v})
    return out


def row_to_post(d: dict, platform: Optional[str], n: int = 0) -> Optional[Post]:
    ts = parse_dt(_pick(d, "created_at"))
    if ts is None:
        return None
    name = str(_pick(d, "author_name") or _pick(d, "author_id") or "unknown")
    return Post(
        id=str(_pick(d, "id") or f"row{n}"), platform=(d.get("platform") or platform or "unknown").lower(),
        author_id=str(_pick(d, "author_id") or name), author_name=name, text=str(_pick(d, "text") or ""),
        created_at=ts, url=str(_pick(d, "url") or ""), likes=_int(_pick(d, "likes")), shares=_int(_pick(d, "shares")),
        replies=_int(_pick(d, "replies")), views=_int(_pick(d, "views")) if _pick(d, "views") is not None else None,
        media=_media(d), author_created=parse_dt(_pick(d, "author_created")),
        author_followers=_int(_pick(d, "author_followers")) if _pick(d, "author_followers") is not None else None,
        author_verified=bool(d.get("author_verified") or d.get("verified")), avatar_hash=_pick(d, "avatar_hash"),
        avatar_is_default=bool(d.get("avatar_is_default")),
        is_reshare=bool(d.get("is_reshare")) or bool(_pick(d, "reshare_of")),
        reshare_of=str(_pick(d, "reshare_of")) if _pick(d, "reshare_of") else None,
        reshare_of_author=str(_pick(d, "reshare_of_author")) if _pick(d, "reshare_of_author") else None,
        reply_to=d.get("reply_to"), lang=d.get("lang"))


def load_file(path: str, platform: Optional[str] = None) -> List[Post]:
    with open(path, encoding="utf-8") as f:
        if path.endswith(".csv"):
            rows = list(csv.DictReader(f))
        elif path.endswith((".jsonl", ".ndjson")):
            rows = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)
            rows = data if isinstance(data, list) else data.get("posts") or data.get("items") or [data]
    posts = [row_to_post(r, platform, i) for i, r in enumerate(rows)]
    return [p for p in posts if p]
