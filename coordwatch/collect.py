"""One entry point that gathers posts from every selected source (live APIs, uploaded exports, demo data)
into the common Post schema. Used by both the CLI and the web app."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from . import secrets_store as S
from .collectors.base import Cancelled, PlatformBlocked
from .filtering import filter_posts
from .models import Post

LIVE = ("x", "youtube", "telegram")
FILE_ONLY = ("tiktok", "instagram", "facebook", "snapchat")
ALL_PLATFORMS = LIVE + FILE_ONLY


def collect_posts(topic: str, since: datetime, until: datetime, platforms: List[str], *, use_demo: bool = False,
                  files: Optional[List[Tuple[str, Optional[str]]]] = None, telegram_channels: str = "",
                  x_archive: bool = False, limit: int = 1000, seed: int = 42, depth: str = "standard",
                  cancelled: Callable[[], bool] = lambda: False, log: Callable[[str], None] = lambda m: None) -> Tuple[List[Post], List[str]]:
    posts: List[Post] = []
    notes: List[str] = []
    if use_demo:
        from .collectors import demo
        got = demo.generate(seed)[0]
        posts += filter_posts(got, topic, since, until)
        notes.append("DEMO MODE: synthetic data with a planted ground truth - not real social-media content.")
        log(f"demo: {len(got)} synthetic posts")
    for path, plat in (files or []):
        from .collectors.fileimport import load_file
        got = filter_posts(load_file(path, plat), topic, since, until)
        posts += got
        log(f"file {path.split('/')[-1].split(chr(92))[-1]}: {len(got)} posts match")
        notes.append(f"Imported from file export ({plat or 'mixed'}): platform APIs were not queried.")
    for pl in platforms:
        if pl not in LIVE:
            continue
        if cancelled():
            raise Cancelled()
        try:
            log(f"{pl}: starting…")
            c = _live_collector(pl, telegram_channels, x_archive, depth)
            c.log, c.cancelled = log, cancelled
            got = c.collect(topic, since, until, limit)      # server-side topic search; no local re-filter
            posts += got
            notes += c.notes
            log(f"{pl}: {len(got)} posts")
        except Cancelled:
            raise
        except PlatformBlocked as e:
            notes.append(f"{pl}: BLOCKED/INCOMPLETE - {e}")
            log(f"{pl}: blocked - {e}")
        except RuntimeError as e:                               # missing keys / setup
            notes.append(f"{pl}: skipped - {e}")
            log(f"{pl}: skipped - {e}")
        except Exception as e:                                  # one bad platform must not kill the run
            logging.exception("collector %s failed", pl)
            notes.append(f"{pl}: failed - {type(e).__name__}: {e}")
            log(f"{pl}: failed - {type(e).__name__}: {e}")
    return posts, notes


DEPTH = {"quick": (12, 100), "standard": (30, 200), "deep": (60, 400)}   # (videos, comments per video)


def _live_collector(pl: str, telegram_channels: str, x_archive: bool, depth: str = "standard"):
    if pl == "x":
        from .collectors.x import XCollector
        return XCollector(bearer=S.get("X_BEARER_TOKEN"), archive=x_archive)
    if pl == "youtube":
        from .collectors.youtube import YouTubeCollector
        mv, mc = DEPTH.get(depth, DEPTH["standard"])
        return YouTubeCollector(api_key=S.get("YOUTUBE_API_KEY"), max_videos=mv, max_comments=mc)
    from .collectors.telegram import TelegramCollector
    if not S.telegram_logged_in():
        raise RuntimeError("Telegram needs a one-time login: run `python -m coordwatch telegram-login` in a terminal.")
    return TelegramCollector([c.strip() for c in telegram_channels.split(",") if c.strip()],
                             api_id=S.get("TELEGRAM_API_ID"), api_hash=S.get("TELEGRAM_API_HASH"),
                             session=S.telegram_session_path())
