"""X (Twitter) through a logged-in browser session (Playwright) - free, EXPERIMENTAL, off unless configured.

How it works: open x.com search (Latest tab, with since:/until:) in Chromium using the cookies of a logged-in account,
scroll slowly, and capture the JSON that X's own web app receives from its `SearchTimeline` GraphQL call.
Parsing structured JSON is far sturdier than scraping HTML, and the payload carries account creation date,
follower count, avatar URL and retweet/quote links - everything the coordination signals need.

Setup: log in to a THROWAWAY X account in a normal browser, export its cookies (any cookie-editor extension, JSON)
to a file and set X_COOKIES_FILE=/path/cookies.json (needs at least auth_token and ct0).  `pip install playwright`
then `playwright install chromium`.

Risks - say them out loud in the interview: this breaks X's terms of service, the account can be rate-limited or
suspended, and X changes its internal schema often.  The parser is defensive (recursive search, field fallbacks),
the loop stops on HTTP 429, a login redirect, an idle timeline or the post cap, and it never tries to evade blocks.
Never use a work account or work network."""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from ..models import Post
from .base import Collector, PlatformBlocked, dhash_bytes, log


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    except ValueError:
        return None


def parse_search_payload(payload: dict) -> Tuple[List[Post], Dict[str, str]]:
    """GraphQL SearchTimeline JSON -> (posts, {author_id: avatar_url}).  Pure function, unit-tested on a fixture."""
    posts, avatars, seen = [], {}, set()
    for d in _walk(payload):
        res = d.get("tweet_results", {}).get("result") if isinstance(d.get("tweet_results"), dict) else None
        if not res:
            continue
        if res.get("__typename") == "TweetWithVisibilityResults":
            res = res.get("tweet", res)
        leg = res.get("legacy") or {}
        tid = res.get("rest_id") or leg.get("id_str")
        created = _dt(leg.get("created_at"))
        if not tid or tid in seen or created is None:
            continue
        seen.add(tid)
        user = (res.get("core", {}).get("user_results", {}).get("result")) or {}
        uleg, ucore = user.get("legacy") or {}, user.get("core") or {}
        handle = ucore.get("screen_name") or uleg.get("screen_name") or ""
        uid = str(user.get("rest_id") or leg.get("user_id_str") or "")
        avatar = (user.get("avatar") or {}).get("image_url") or uleg.get("profile_image_url_https") or ""
        media = []
        for m in (leg.get("extended_entities") or leg.get("entities") or {}).get("media", []):
            if m.get("type") == "photo":
                media.append({"type": "photo", "url": m.get("media_url_https", "")})
            elif m.get("type") in ("video", "animated_gif"):
                vs = [v for v in m.get("video_info", {}).get("variants", []) if v.get("content_type") == "video/mp4"]
                if vs:
                    media.append({"type": "video", "url": max(vs, key=lambda v: v.get("bitrate", 0))["url"]})
        rt = (leg.get("retweeted_status_result") or {}).get("result") or {}
        rt = rt.get("tweet", rt)
        rt_user = (rt.get("core", {}).get("user_results", {}).get("result")) or {}
        views = (res.get("views") or {}).get("count")
        verified = bool(user.get("is_blue_verified") or uleg.get("verified") or (user.get("verification") or {}).get("verified"))
        posts.append(Post(
            id=str(tid), platform="x", author_id=uid, author_name=handle, text=leg.get("full_text", ""), created_at=created,
            url=f"https://x.com/{handle or 'i'}/status/{tid}", likes=int(leg.get("favorite_count", 0)),
            shares=int(leg.get("retweet_count", 0)) + int(leg.get("quote_count", 0)), replies=int(leg.get("reply_count", 0)),
            views=int(views) if str(views).isdigit() else None, media=media,
            author_created=_dt(ucore.get("created_at") or uleg.get("created_at")),
            author_followers=int(uleg["followers_count"]) if "followers_count" in uleg else None, author_verified=verified,
            avatar_is_default=bool(uleg.get("default_profile_image")),
            is_reshare=bool(rt), reshare_of=str(rt.get("rest_id")) if rt.get("rest_id") else (leg.get("quoted_status_id_str") or None),
            reshare_of_author=str(rt_user.get("rest_id")) if rt_user.get("rest_id") else None,
            reply_to=leg.get("in_reply_to_status_id_str") or None, lang=leg.get("lang")))
        if uid and avatar:
            avatars.setdefault(uid, avatar)
    return posts, avatars


class XBrowser(Collector):
    platform = "x"
    notes = ["X (browser session, experimental): reads X's own web search with a throwaway logged-in account. Violates X's ToS, "
             "can be rate-limited or suspended, and depends on X's internal schema. Results are a sample of what search returns, not a full archive."]

    def __init__(self, cookies_file: Optional[str] = None, max_scrolls: int = 60, headless: bool = True, max_avatars: int = 60):
        self.cookies_file = cookies_file or os.environ.get("X_COOKIES_FILE", "")
        if not self.cookies_file or not os.path.exists(self.cookies_file):
            raise RuntimeError("X needs X_COOKIES_FILE (cookie export of a throwaway X login) or a paid X_BEARER_TOKEN - see README.")
        self.max_scrolls, self.headless, self.max_avatars = max_scrolls, headless, max_avatars
        self.chrome = os.environ.get("CHROME_PATH") or None

    @staticmethod
    def _cookies(path: str) -> list:
        cookies = json.load(open(path, encoding="utf-8"))
        for c in cookies:                                           # browser-extension export -> playwright format
            c.setdefault("domain", ".x.com")
            c.setdefault("path", "/")
            c["sameSite"] = {"no_restriction": "None", "lax": "Lax", "strict": "Strict"}.get(str(c.get("sameSite", "")).lower(), "Lax")
            for k in ("hostOnly", "session", "storeId", "id"):
                c.pop(k, None)
            if "expirationDate" in c:
                c["expires"] = c.pop("expirationDate")
        return cookies

    def collect(self, topic: str, since: datetime, until: datetime, limit: int = 1000) -> List[Post]:
        from playwright.sync_api import sync_playwright
        q = f"{topic} since:{since:%Y-%m-%d} until:{until:%Y-%m-%d}"
        url = "https://x.com/search?q=" + quote(q) + "&src=typed_query&f=live"
        posts: Dict[str, Post] = {}
        avatars: Dict[str, str] = {}
        stop = {"why": ""}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless, executable_path=self.chrome)
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
            ctx.add_cookies(self._cookies(self.cookies_file))
            page = ctx.new_page()

            def on_response(resp):
                try:
                    if resp.status == 429:
                        stop["why"] = "HTTP 429 rate limit"
                    elif "SearchTimeline" in resp.url and resp.status == 200:
                        p, a = parse_search_payload(resp.json())
                        for x in p:
                            posts.setdefault(x.id, x)
                        for k, v in a.items():
                            avatars.setdefault(k, v)
                except Exception as e:                              # a parse error must never kill the loop
                    log.debug("x response parse: %s", e)

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            idle = 0
            for i in range(self.max_scrolls):
                self._check()
                before = len(posts)
                page.mouse.wheel(0, random.randint(1800, 2800))
                time.sleep(random.uniform(2.5, 6.0))                # human-paced, never hammered
                if "login" in page.url or "i/flow" in page.url:
                    stop["why"] = "redirected to login (cookies invalid or expired)"
                if stop["why"]:
                    break
                idle = idle + 1 if len(posts) == before else 0
                if idle >= 4:
                    stop["why"] = "end of timeline"
                    break
                if len(posts) >= limit:
                    stop["why"] = "post limit reached"
                    break
                if i % 5 == 4:
                    self.log(f"x: {len(posts)} posts after {i + 1} scrolls")
            hashes: Dict[str, Optional[str]] = {}
            for uid, u in list(avatars.items())[: self.max_avatars]:  # best effort, capped, same session
                try:
                    hashes[uid] = dhash_bytes(ctx.request.get(u.replace("_normal", "_400x400"), timeout=15000).body())
                except Exception:
                    hashes[uid] = None
            browser.close()
        for p in posts.values():
            p.avatar_hash = hashes.get(p.author_id)
        log.info("x-browser: %d posts (%s)", len(posts), stop["why"] or "scroll limit")
        if not posts and stop["why"] and stop["why"] != "end of timeline":
            raise PlatformBlocked(f"X browser session stopped: {stop['why']}")
        return [p for p in posts.values() if since <= p.created_at <= until][:limit]
