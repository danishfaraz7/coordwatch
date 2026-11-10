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
                for term in topic_terms(topic, combined=True):
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

    async def _search_global(self, client, topic, since: datetime, until: datetime, limit: int, posts: List[Post], errors, seen):
        """messages.searchGlobal: Telegram's global message search. Telegram ranks the account's own chats first, so results can include
        channels you have joined; those are dropped unless TELEGRAM_INCLUDE_JOINED=1.  Search every public channel/group at once.  Pages with Telegram's (rate, peer, id) cursor; the server match is
        fuzzy, so every hit is re-checked locally against the topic and the date window.  Each query is tried as written
        and without its leading '#' (hashtag syntax is not always honoured by the server), and the date window is applied
        locally (results arrive newest first) so a server-side date quirk cannot hide everything."""
        from telethon.tl import functions, types
        from ..filtering import matches_topic, topic_terms
        channels, raw_total = set(), 0
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
                    if cid in getattr(self, "_joined", ()):
                        self._skipped.setdefault(cid, set()).add(m.id)
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
        self.log(f"telegram: searchGlobal: {len(channels)} channel(s), {raw_total} raw results")

    async def _global(self, client, topic, since: datetime, until: datetime, limit: int, posts: List[Post], errors):
        """No channels named: try three ways to find where the topic is discussed, in order of how wide they reach.
        1. channels.searchPosts - Telegram's public post / hashtag search (newer API; free quota is small, may be paid).
        2. channel directory   - contacts.search finds public channels/groups whose name or @username matches the topic words,
                                 then each is searched server-side.
        3. messages.searchGlobal - Telegram's own global message search over public channels and groups (not limited to the account's
                                 subscriptions; results depend on Telegram's index and ranking).
        Telegram also returns hits from channels the account has joined. Only their ids are listed (never their messages) so those hits
        can be dropped and the results stay a public-Telegram view; set TELEGRAM_INCLUDE_JOINED=1 to keep them."""
        seen = set()
        self._joined, self._skipped = set(), {}
        if os.environ.get("TELEGRAM_INCLUDE_JOINED", "").lower() not in ("1", "true", "yes"):
            try:
                async for dlg in client.iter_dialogs(limit=None):
                    self._joined.add(dlg.entity.id)
                self.log(f"telegram: your account has joined {len(self._joined)} chat(s); results from them are excluded so this stays a public search")
            except Exception as e:
                self.log(f"telegram: could not list joined chats ({type(e).__name__}); joined channels are not excluded")
        for name, fn in (("public post search", self._search_posts), ("channel directory", self._search_directory),
                         ("searchGlobal", self._search_global)):
            self._check()
            before = len(posts)
            try:
                await fn(client, topic, since, until, limit, posts, errors, seen)
            except Exception as e:
                if type(e).__name__ == "Cancelled":
                    raise
                self.log(f"telegram: {name} failed - {type(e).__name__}: {e}")
            self.log(f"telegram: {name}: +{len(posts) - before} messages (total {len(posts)})")
            if len(posts) >= limit:
                break
        if self._skipped:
            self.log(f"telegram: excluded {sum(len(v) for v in self._skipped.values())} message(s) from {len(self._skipped)} channel(s) you have joined "
                     f"(set TELEGRAM_INCLUDE_JOINED=1 to keep them)")
        n = len({p.author_id for p in posts})
        self.log(f"telegram: search done - {len(posts)} messages from {n} account(s)/channel(s)")
        if not posts:
            self.log("telegram: nothing found by any route. The topic may simply not be discussed on public Telegram in this window, or "
                     "Telegram limits search for this (new) account. Name channels in the Telegram channels box to read them directly.")

    def _add(self, m, chats, users, seen, topic, since, until, posts) -> bool:
        peer = m.peer_id
        cid = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
        if cid is None or (cid, m.id) in seen:
            return False
        from ..filtering import matches_topic
        d = m.date if m.date.tzinfo else m.date.replace(tzinfo=timezone.utc)
        if d < since or d > until or not matches_topic(m.message or "", topic):
            return False
        if cid in getattr(self, "_joined", ()):
            self._skipped.setdefault(cid, set()).add(m.id)
            return False
        seen.add((cid, m.id))
        chat = chats.get(cid)
        uid = getattr(getattr(m, "from_id", None), "user_id", None)
        if uid in users:
            try:
                m._sender = users[uid]
            except Exception:
                pass
        posts.append(message_to_post(m, getattr(chat, "username", None) or "", str(cid), getattr(chat, "title", "") or str(cid)))
        return True

    async def _search_posts(self, client, topic, since, until, limit, posts, errors, seen):
        from telethon.tl import functions, types
        from ..filtering import topic_terms
        for term in topic_terms(topic):
            self._check()
            kw = {"hashtag": term.lstrip("#")} if term.startswith("#") and " " not in term else {"query": term}
            rate, off_id, off_peer, pages, got = 0, 0, types.InputPeerEmpty(), 0, 0
            self.log(f"telegram: public post search for {kw}…")
            while pages < 20 and got < limit:
                try:
                    res = await client(functions.channels.SearchPostsRequest(offset_rate=rate, offset_peer=off_peer, offset_id=off_id, limit=100, **kw))
                except errors.FloodWaitError as e:
                    self.log(f"telegram: rate limited by Telegram - waiting {min(e.seconds, 60)}s…")
                    await asyncio.sleep(min(e.seconds, 60) + 1)
                    if e.seconds > 60:
                        return
                    continue
                pages += 1
                msgs = [m for m in res.messages if isinstance(m, types.Message)]
                if not msgs:
                    self.log(f"telegram: public post search: no messages on page {pages}")
                    break
                chats = {c.id: c for c in getattr(res, "chats", [])}
                users = {u.id: u for u in getattr(res, "users", [])}
                kept = sum(self._add(m, chats, users, seen, topic, since, until, posts) for m in msgs)
                got += kept
                dates = [m.date for m in msgs]
                self.log(f"telegram: public post search page {pages}: {len(msgs)} returned (newest {max(dates):%Y-%m-%d}, oldest {min(dates):%Y-%m-%d}), {kept} kept")
                nxt = getattr(res, "next_rate", None)
                od = min(dates) if min(dates).tzinfo else min(dates).replace(tzinfo=timezone.utc)
                if nxt is None or od < since:
                    break
                try:
                    off_peer = await client.get_input_entity(msgs[-1].peer_id)
                except Exception:
                    break
                rate, off_id = nxt, msgs[-1].id
                await asyncio.sleep(1.0)

    async def _search_directory(self, client, topic, since, until, limit, posts, errors, seen, max_channels: int = 25):
        import re as _re
        from telethon.tl import functions, types
        from ..filtering import topic_terms
        words = []
        for term in topic_terms(topic):
            for q in (term.lstrip("#"), _re.sub(r"\bvs\.?\b", " ", term.lstrip("#"))):
                q = " ".join(q.split())
                if len(q) >= 3 and q not in words:
                    words.append(q)
        cands = {}
        for q in words:
            self._check()
            try:
                res = await client(functions.contacts.SearchRequest(q=q, limit=30))
            except errors.FloodWaitError as e:
                self.log(f"telegram: rate limited - waiting {min(e.seconds, 60)}s…")
                await asyncio.sleep(min(e.seconds, 60) + 1)
                continue
            found = [c for c in getattr(res, "chats", []) if isinstance(c, types.Channel) and getattr(c, "username", None)]
            self.log(f"telegram: directory '{q}': {len(found)} public channel/group(s) match by name")
            for c in found:
                cands.setdefault(c.id, c)
            await asyncio.sleep(0.5)
        for ent in list(cands.values())[:max_channels]:
            self._check()
            kept = 0
            for term in topic_terms(topic):
                try:
                    async for m in client.iter_messages(ent, search=term, offset_date=until, limit=min(limit, 300)):
                        d = m.date if m.date.tzinfo else m.date.replace(tzinfo=timezone.utc)
                        if d < since:
                            break
                        kept += self._add(m, {ent.id: ent}, {}, seen, topic, since, until, posts)
                except errors.FloodWaitError as e:
                    self.log(f"telegram: rate limited - waiting {min(e.seconds, 60)}s…")
                    await asyncio.sleep(min(e.seconds, 60) + 1)
                except Exception as e:
                    self.log(f"telegram: @{ent.username}: {type(e).__name__}: {e}")
                    break
            self.log(f"telegram: @{ent.username} ({getattr(ent, 'title', '')}): {kept} matching message(s) in the window")
            await asyncio.sleep(0.7)
