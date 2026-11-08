"""Telegram public web preview (https://t.me/s/<channel>) - free, no login, no API credentials.

Used automatically when Telethon is not set up.  It reads the channels you list (or that discovery finds) and filters
their posts by topic locally; there is no global Telegram search for normal accounts.  Pagination uses
`?before=<message id>` and stops once messages are older than the start date.
Limits: channels only (the preview does not show group chats), no reactions, no account metadata."""
from __future__ import annotations

import random
import re
import time
from datetime import datetime
from typing import List

from ..filtering import matches_topic
from ..models import Post, parse_dt
from .base import Collector, PlatformBlocked, log

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWeb" "Kit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_bg = re.compile(r"url\('?([^')]+)'?\)")


def _num(s: str) -> int:
    s = (s or "").strip().upper().replace(",", "")
    mult = 1000 if s.endswith("K") else 1_000_000 if s.endswith("M") else 1
    try:
        return int(float(s.rstrip("KM")) * mult)
    except ValueError:
        return 0


def parse_page(html: str, channel: str) -> List[Post]:
    """One t.me/s page -> Posts (pure function, unit-tested on a fixture)."""
    from bs4 import BeautifulSoup
    out = []
    for m in BeautifulSoup(html, "html.parser").select("div.tgme_widget_message[data-post]"):
        data_post = m["data-post"]                       # "channel/123"
        t = m.select_one("time[datetime]")
        if not t:
            continue
        txt = m.select_one(".tgme_widget_message_text")
        text = txt.get_text("\n").strip() if txt else ""
        media = [{"type": "photo", "url": mm.group(1)} for a in m.select("a.tgme_widget_message_photo_wrap")
                 if (mm := _bg.search(a.get("style", "")))]
        media += [{"type": "video", "url": v.get("src") or f"https://t.me/{data_post}"} for v in m.select("video")] \
            or ([{"type": "video", "url": f"https://t.me/{data_post}"}] if m.select(".tgme_widget_message_video_wrap") else [])
        views = m.select_one(".tgme_widget_message_views")
        fwd = m.select_one(".tgme_widget_message_forwarded_from_name")
        origin, origin_author = None, None
        if fwd is not None:
            mm = re.search(r"t\.me/([^/?#]+)/(\d+)", fwd.get("href", "") or "")
            if mm:
                origin_author, origin = mm.group(1), f"{mm.group(1)}/{mm.group(2)}"
            else:
                origin_author = fwd.get_text(strip=True) or None
        out.append(Post(id=data_post, platform="telegram", author_id=channel, author_name=channel, text=text,
                        created_at=parse_dt(t["datetime"]), url=f"https://t.me/{data_post}", views=_num(views.get_text()) if views else None,
                        media=media, is_reshare=bool(fwd is not None and not text), reshare_of=origin, reshare_of_author=origin_author))
    return out


class TelegramWeb(Collector):
    platform = "telegram"
    notes = ["Telegram (public web preview, no login): only the listed public channels are read and filtered by topic locally; "
             "reactions, groups and account metadata are not available, so the account-age and avatar signals do not apply."]

    def __init__(self, channels: List[str], max_pages: int = 15, pause=(1.0, 2.5)):
        self.channels = [c.strip().lstrip("@").replace("https://t.me/", "").replace("s/", "").strip("/") for c in channels if c.strip()]
        if not self.channels:
            raise RuntimeError("Telegram needs channels: pass --telegram-channels @a,@b (or use --discover to find some).")
        self.max_pages, self.pause = max_pages, pause

    def _page(self, channel: str, before):
        import requests
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        for attempt in range(4):
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=25)
            if r.status_code in (429, 502, 503):
                delay = float(r.headers["Retry-After"]) + 1 if r.headers.get("Retry-After", "").isdigit() else 2 ** attempt * 3 + random.random()
                self.log(f"telegram: HTTP {r.status_code} on {channel} - waiting {delay:.0f}s")
                time.sleep(min(delay, 120))
                continue
            r.raise_for_status()
            return r.text
        raise PlatformBlocked(f"t.me rate-limited the preview for {channel}; partial results kept, rerun later.")

    def collect(self, topic: str, since: datetime, until: datetime, limit: int = 1000) -> List[Post]:
        posts: List[Post] = []
        total_scanned, oldest_seen = 0, None
        for ch in self.channels:
            before, scanned = None, 0
            for _ in range(self.max_pages):
                self._check()
                try:
                    page = parse_page(self._page(ch, before), ch)
                except PlatformBlocked:
                    raise
                except Exception as e:                  # one bad channel must not kill the run
                    log.warning("telegram-web %s: %s", ch, e)
                    self.log(f"telegram: {ch} unreadable ({type(e).__name__}) - skipped")
                    break
                if not page:                            # private / non-existent / preview disabled
                    break
                scanned += len(page)
                total_scanned += len(page)
                posts += [p for p in page if since <= p.created_at <= until and matches_topic(p.text, topic)]
                oldest = min(page, key=lambda p: p.created_at)
                oldest_seen = oldest.created_at if oldest_seen is None else min(oldest_seen, oldest.created_at)
                if oldest.created_at < since:
                    break
                before = oldest.id.split("/")[-1]
                time.sleep(random.uniform(*self.pause))
            self.log(f"telegram: {ch}: scanned {scanned} messages")
            if len(posts) >= limit:
                break
        self.log(f"telegram: scanned {total_scanned} messages in {len(self.channels)} channel(s) "
                 f"(oldest {oldest_seen:%Y-%m-%d}); {len(posts)} matched the topic inside {since:%Y-%m-%d}..{until:%Y-%m-%d}"
                 if oldest_seen else f"telegram: no readable messages in {len(self.channels)} channel(s)")
        return posts[:limit]
