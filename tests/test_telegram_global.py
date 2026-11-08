import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from telethon import errors
from telethon.tl import types

from coordwatch.collectors.telegram import TelegramCollector

S = datetime(2026, 11, 6, tzinfo=timezone.utc)
U = S + timedelta(days=3)


def msg(i, cid, text, hours):
    return types.Message(id=i, peer_id=types.PeerChannel(cid), date=S + timedelta(hours=hours), message=text, post=True, views=10)


class FakeClient:
    """Stands in for TelegramClient: two pages of results, then nothing."""
    def __init__(self):
        self.calls = []
        chan = types.Channel(id=7, title="Cricket Chat", photo=types.ChatPhotoEmpty(), date=S, username="crickchat")
        self.pages = [
            NS(messages=[msg(1, 7, "India vs NZ #indvsnz what a game", 2), msg(2, 7, "unrelated chatter", 3)], chats=[chan], users=[], next_rate=5),
            NS(messages=[msg(3, 7, "#IndVsNZ second page", 30), msg(1, 7, "India vs NZ #indvsnz what a game", 2)], chats=[chan], users=[], next_rate=None),
        ]

    async def __call__(self, req):
        self.calls.append(req)
        return self.pages.pop(0) if self.pages else NS(messages=[], chats=[], users=[], next_rate=None)

    async def get_input_entity(self, peer):
        return types.InputPeerChannel(channel_id=7, access_hash=1)


class GlobalSearchTests(unittest.TestCase):
    def test_pages_filters_and_dedupes(self):
        c = TelegramCollector([], api_id=1, api_hash="x")
        c.log, c.cancelled = (lambda *_: None), (lambda: False)
        posts = []
        asyncio.run(c._global(FakeClient(), "#indvsnz", S, U, 500, posts, errors))
        self.assertEqual([p.id for p in posts], ["7/1", "7/3"])          # off-topic message and the duplicate are dropped
        self.assertEqual(posts[0].url, "https://t.me/crickchat/1")
        self.assertEqual(posts[0].platform, "telegram")

    def test_falls_back_to_query_without_hash_and_reports_empty(self):
        c = TelegramCollector([], api_id=1, api_hash="x")
        logs = []
        c.log, c.cancelled = logs.append, (lambda: False)
        fc = FakeClient()
        fc.pages = []                                                    # Telegram returns nothing for every query
        asyncio.run(c._global(fc, "#indvsnz", S, U, 500, [], errors))
        self.assertEqual(len(fc.calls), 2)                               # '#indvsnz' then 'indvsnz'
        self.assertTrue(any("no messages at all" in l for l in logs))

    def test_channels_are_optional(self):
        TelegramCollector([], api_id=1, api_hash="x")                     # used to raise: now means "search everything"


if __name__ == "__main__":
    unittest.main()
