"""Telegram collector via Telethon (MTProto user API; public channels/groups only).
Needs TELEGRAM_API_ID / TELEGRAM_API_HASH (my.telegram.org) and a one-time login for the session file.
Telegram has no global historical search for normal accounts, so you give it a list of public channels
or groups to monitor (--telegram-channels @a,@b) and it uses server-side `search=` inside each.
Telethon handles most flood limits internally; we additionally catch FloodWaitError and sleep."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import List

from ..models import Post
from .base import Collector, PlatformBlocked, log


def message_to_post(m, chat_username: str, chat_id: str, chat_title: str) -> Post:
    """Pure conversion so it can be unit-tested with a stub message object."""
    sender_id = str(getattr(m, "sender_id", None) or chat_id)
    is_channel_post = bool(getattr(m, "post", False))
    author_id = chat_id if is_channel_post else sender_id
    author_name = chat_username or chat_title if is_channel_post else (
        getattr(getattr(m, "sender", None), "username", None) or sender_id)
    fwd = getattr(m, "fwd_from", None)
    fwd_from = None
    if fwd is not None and getattr(fwd, "from_id", None) is not None:
        fid = fwd.from_id
        fwd_from = str(getattr(fid, "channel_id", None) or getattr(fid, "user_id", None) or "")
    reactions = 0
    for r in (getattr(getattr(m, "reactions", None), "results", None) or []):
        reactions += r.count
    media = []
    if getattr(m, "photo", None):
        media.append({"type": "photo", "url": f"https://t.me/{chat_username}/{m.id}"})
    if getattr(m, "video", None) or getattr(m, "gif", None):
        media.append({"type": "video", "url": f"https://t.me/{chat_username}/{m.id}"})
    date = m.date if m.date.tzinfo else m.date.replace(tzinfo=timezone.utc)
    return Post(
        id=f"{chat_id}/{m.id}", platform="telegram", author_id=author_id, author_name=author_name,
        text=m.message or "", created_at=date, url=f"https://t.me/{chat_username}/{m.id}" if chat_username else "",
        likes=reactions, shares=getattr(m, "forwards", 0) or 0,
        replies=getattr(getattr(m, "replies", None), "replies", 0) or 0, views=getattr(m, "views", None), media=media,
        is_reshare=bool(fwd_from and not (m.message or "").strip()), reshare_of_author=fwd_from,
        reshare_of=(f"{fwd_from}/{fwd.channel_post}" if fwd_from and getattr(fwd, "channel_post", None) else None))


class TelegramCollector(Collector):
    platform = "telegram"
    notes = ["Telegram: public channels/groups you list only (no global search). Account creation dates and profile "
             "photo hashes are not exposed by the API, so those two coordination signals are unavailable here."]

    def __init__(self, channels: List[str], api_id: int = None, api_hash: str = None, session: str = "coordwatch"):
        self.channels = [c.lstrip("@") for c in channels]
        self.api_id = int(api_id or os.environ.get("TELEGRAM_API_ID", 0))
        self.api_hash = api_hash or os.environ.get("TELEGRAM_API_HASH")
        if not (self.api_id and self.api_hash):
            raise RuntimeError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH (https://my.telegram.org).")
        if not self.channels:
            raise RuntimeError("Telegram needs --telegram-channels @chan1,@chan2")
        self.session = session

    def collect(self, topic, since, until, limit=1000):
        return asyncio.run(self._collect(topic, since, until, limit))

    async def _collect(self, topic, since: datetime, until: datetime, limit: int):
        try:
            from telethon import TelegramClient, errors
        except ImportError as e:
            raise RuntimeError("pip install telethon") from e
        from ..filtering import topic_terms
        posts: List[Post] = []
        async with TelegramClient(self.session, self.api_id, self.api_hash) as client:
            for ch in self.channels:
                try:
                    ent = await client.get_entity(ch)
                except Exception as e:
                    log.warning("telegram: cannot resolve %s (%s) - skipped", ch, e)
                    continue
                for term in topic_terms(topic):
                    self._check()
                    self.log(f"telegram: searching {ch} for '{term}'…")
                    while True:
                        try:
                            async for m in client.iter_messages(ent, search=term, offset_date=until, limit=limit):
                                d = m.date if m.date.tzinfo else m.date.replace(tzinfo=timezone.utc)
                                if d < since:
                                    break
                                posts.append(message_to_post(m, getattr(ent, "username", ch), str(ent.id),
                                                             getattr(ent, "title", ch)))
                                if len(posts) % 50 == 0:
                                    self._check()
                                    self.log(f"telegram: {len(posts)} messages so far")
                            break
                        except errors.FloodWaitError as e:
                            log.warning("telegram FloodWait %ss on %s - sleeping", e.seconds, ch)
                            await asyncio.sleep(e.seconds + 1)
                        except (errors.ChannelPrivateError, errors.ChatAdminRequiredError) as e:
                            raise PlatformBlocked(f"{ch}: not a public channel / access denied ({e})")
        return posts
