"""Telegram collector via Telethon (MTProto user API; public channels/groups only).
Needs TELEGRAM_API_ID / TELEGRAM_API_HASH (my.telegram.org) and a one-time login for the session file.
With no channels given it uses Telegram's own global search (messages.searchGlobal) over public channels and groups, so
you do not have to know where the topic is discussed. If you do name channels (--telegram-channels @a,@b) it searches
only inside those, using the server-side `search=`.
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
    notes = ["Telegram API: global search over public channels and groups (Telegram's own index and ranking, so it can miss "
             "messages), or only the channels you listed. Account creation dates and profile photo hashes are not exposed by the "
             "API, so those two coordination signals are unavailable here."]

    def __init__(self, channels: List[str], api_id: int = None, api_hash: str = None, session: str = "coordwatch"):
        self.channels = [c.lstrip("@") for c in channels]
        self.api_id = int(api_id or os.environ.get("TELEGRAM_API_ID", 0))
        self.api_hash = api_hash or os.environ.get("TELEGRAM_API_HASH")
        if not (self.api_id and self.api_hash):
            raise RuntimeError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH (https://my.telegram.org).")
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
            if not self.channels:
                await self._global(client, topic, since, until, limit, posts, errors)
                return posts
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

    async def _global(self, client, topic, since: datetime, until: datetime, limit: int, posts: List[Post], errors):
        """Search every public channel/group at once.  Pages with Telegram's (rate, peer, id) cursor; the server match is
        fuzzy, so every hit is re-checked locally against the topic and the date window.  Each query is tried as written
        and without its leading '#' (hashtag syntax is not always honoured by the server), and the date window is applied
        locally (results arrive newest first) so a server-side date quirk cannot hide everything."""
        from telethon.tl import functions, types
        from ..filtering import matches_topic, topic_terms
        seen, channels, raw_total = set(), set(), 0
        queries = []
        for term in topic_terms(topic):
            for q in (term, term.lstrip("#")):
                if q and q not in queries:
                    queries.append(q)
        for q in queries:
            self._check()
            self.log(f"telegram: global search for '{q}' across public channels…")
            rate, off_id, off_peer, got, pages = 0, 0, types.InputPeerEmpty(), 0, 0
            while got < limit and pages < 40:
                self._check()
                try:
                    res = await client(functions.messages.SearchGlobalRequest(
                        q=q, filter=types.InputMessagesFilterEmpty(), min_date=None, max_date=None,
                        offset_rate=rate, offset_peer=off_peer, offset_id=off_id, limit=100))
                except errors.FloodWaitError as e:
                    log.warning("telegram FloodWait %ss on global search - sleeping", e.seconds)
                    self.log(f"telegram: rate limited by Telegram - waiting {e.seconds}s…")
                    await asyncio.sleep(e.seconds + 1)
                    continue
                pages += 1
                msgs = [m for m in res.messages if isinstance(m, types.Message)]
                raw_total += len(msgs)
                if not msgs:
                    self.log(f"telegram: '{q}': Telegram returned no messages on page {pages}")
                    break
                dates = [m.date for m in msgs]
                chats = {c.id: c for c in getattr(res, "chats", [])}
                users = {u.id: u for u in getattr(res, "users", [])}
                kept = 0
                for m in msgs:
                    peer = m.peer_id
                    cid = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
                    if cid is None or (cid, m.id) in seen:
                        continue
                    d = m.date if m.date.tzinfo else m.date.replace(tzinfo=timezone.utc)
                    if d < since or d > until or not matches_topic(m.message or "", topic):
                        continue
                    seen.add((cid, m.id))
                    chat = chats.get(cid)
                    uid = getattr(getattr(m, "from_id", None), "user_id", None)
                    if uid in users:
                        try:
                            m._sender = users[uid]
                        except Exception:
                            pass
                    posts.append(message_to_post(m, getattr(chat, "username", None) or "", str(cid), getattr(chat, "title", "") or str(cid)))
                    channels.add(cid)
                    got += 1
                    kept += 1
                self.log(f"telegram: '{q}' page {pages}: {len(msgs)} returned (newest {max(dates):%Y-%m-%d}, oldest {min(dates):%Y-%m-%d}), "
                         f"{kept} kept for the window/topic; {got} total from {len(channels)} channel(s)")
                nxt = getattr(res, "next_rate", None)
                oldest = min(dates) if min(dates).tzinfo else min(dates).replace(tzinfo=timezone.utc)
                if nxt is None or oldest < since:                 # no further page, or we have paged back past the window
                    break
                last = msgs[-1]
                try:
                    off_peer = await client.get_input_entity(last.peer_id)
                except Exception:
                    break
                rate, off_id = nxt, last.id
                await asyncio.sleep(1.0)                          # be gentle: searchGlobal is rate limited
        if raw_total == 0:
            self.log("telegram: Telegram returned no messages at all for any query. Likely causes: the account is new/throwaway and "
                     "Telegram limits global search for it, or this feature needs the account to have joined or used Telegram for a while. "
                     "Name channels (Telegram channels box) as a workaround.")
        self.log(f"telegram: global search done - {len(posts)} messages from {len(channels)} channel(s) ({raw_total} raw results seen)")
