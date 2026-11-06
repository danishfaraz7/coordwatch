"""X (Twitter) API v2 collector. Requires a paid API tier: `recent` search covers 7 days; full-archive
(`all`) needs Pro/Enterprise. Set X_BEARER_TOKEN. Not exercised live in the repo tests; the response
parser is unit-tested against the documented payload shape."""
from __future__ import annotations

import os
from typing import Dict, List

from ..models import Post, parse_dt
from .base import Collector, HttpClient, avatar_hash_from_url

URLS = {"recent": "https://api.x.com/2/tweets/search/recent", "all": "https://api.x.com/2/tweets/search/all"}


def parse_response(d: dict, avatar_hasher=lambda url: None) -> List[Post]:
    inc = d.get("includes", {})
    users = {u["id"]: u for u in inc.get("users", [])}
    media = {m["media_key"]: m for m in inc.get("media", [])}
    ref_tweets = {t["id"]: t for t in inc.get("tweets", [])}
    out = []
    for t in d.get("data", []):
        u = users.get(t["author_id"], {})
        pm = t.get("public_metrics", {})
        refs = {r["type"]: r["id"] for r in t.get("referenced_tweets", [])}
        rt = refs.get("retweeted")
        orig_author = (ref_tweets.get(rt) or {}).get("author_id") if rt else None
        text = t.get("text", "")
        if rt and rt in ref_tweets:                       # expand truncated "RT @x: ..." text
            text = ref_tweets[rt].get("text", text)
        meds = []
        for k in (t.get("attachments") or {}).get("media_keys", []):
            m = media.get(k, {})
            meds.append({"type": "video" if m.get("type") in ("video", "animated_gif") else "photo",
                         "url": m.get("url") or m.get("preview_image_url", "")})
        uname = u.get("username", t["author_id"])
        out.append(Post(
            id=t["id"], platform="x", author_id=t["author_id"], author_name=uname, text=text,
            created_at=parse_dt(t["created_at"]), url=f"https://x.com/{uname}/status/{t['id']}",
            likes=pm.get("like_count", 0), shares=pm.get("retweet_count", 0) + pm.get("quote_count", 0),
            replies=pm.get("reply_count", 0), views=pm.get("impression_count"), media=meds,
            author_created=parse_dt(u.get("created_at")), author_followers=(u.get("public_metrics") or {}).get("followers_count"),
            author_verified=bool(u.get("verified")), avatar_hash=avatar_hasher(u.get("profile_image_url", "")),
            avatar_is_default="default_profile_images" in (u.get("profile_image_url") or ""),
            is_reshare=bool(rt), reshare_of=rt, reshare_of_author=orig_author, reply_to=refs.get("replied_to"),
            lang=t.get("lang")))
    return out


class XCollector(Collector):
    platform = "x"
    notes = ["X: paid API only. `recent` endpoint = last 7 days; deleted/suspended accounts' posts are not returned, "
             "so earliest-post (origin) findings can be biased toward surviving accounts."]

    def __init__(self, bearer: str = None, archive: bool = False, client: HttpClient = None, hash_avatars=True):
        self.bearer = bearer or os.environ.get("X_BEARER_TOKEN")
        if not self.bearer:
            raise RuntimeError("Set X_BEARER_TOKEN (developer.x.com, Basic tier or above).")
        self.url = URLS["all" if archive else "recent"]
        self.c = client or HttpClient(min_interval=1.0, cache_dir=".cache/x")
        self.hash_avatars = hash_avatars

    def collect(self, topic, since, until, limit=1000):
        from ..filtering import topic_terms
        q = "(" + " OR ".join(f'"{t}"' if " " in t else t for t in topic_terms(topic)) + ")"
        params = {"query": q, "max_results": 100, "start_time": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "end_time": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "tweet.fields": "created_at,public_metrics,referenced_tweets,attachments,lang,author_id",
                  "expansions": "author_id,attachments.media_keys,referenced_tweets.id",
                  "user.fields": "created_at,profile_image_url,public_metrics,verified",
                  "media.fields": "type,url,preview_image_url"}
        hasher = (lambda u: avatar_hash_from_url(self.c, u.replace("_normal", "_400x400"))) if self.hash_avatars else (lambda u: None)
        posts: List[Post] = []
        while len(posts) < limit:
            d = self.c.get_json(self.url, params, {"Authorization": f"Bearer {self.bearer}"})
            posts += parse_response(d, hasher)
            nt = (d.get("meta") or {}).get("next_token")
            if not nt:
                break
            params["next_token"] = nt
        return posts[:limit]
