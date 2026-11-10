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
                  cancelled: Callable[[], bool] = lambda: False, log: Callable[[str], None] = lambda m: None,
                  notes_out: Optional[List[str]] = None) -> Tuple[List[Post], List[str]]:
    posts: List[Post] = []
    notes: List[str] = notes_out if notes_out is not None else []      # caller may pass a list it keeps even if we raise
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
        got, used = _run_chain(pl, topic, since, until, limit, telegram_channels, x_archive, depth, cancelled, log, notes)
        posts += got
    return posts, notes


DEPTH = {"quick": (12, 100), "standard": (30, 200), "deep": (60, 400)}   # (videos, comments per video)


def _tg_api_ready() -> bool:
    return bool(S.get("TELEGRAM_API_ID") and S.get("TELEGRAM_API_HASH") and S.telegram_logged_in())


def _chain(pl: str, telegram_channels: str, x_archive: bool, depth: str):
    """Ordered [(label, factory)] for a platform: official/paid route first, free fallback after.
    A factory raises RuntimeError when its credentials are missing, which simply moves on to the next route."""
    mv, mc = DEPTH.get(depth, DEPTH["standard"])
    if pl == "x":
        def api():
            from .collectors.x import XCollector
            return XCollector(bearer=S.get("X_BEARER_TOKEN"), archive=x_archive)

        def browser():
            from .collectors.x_browser import XBrowser
            return XBrowser(cookies_file=S.get("X_COOKIES_FILE"), max_scrolls={"quick": 15, "standard": 40, "deep": 80}.get(depth, 40))
        def web_index():
            from .collectors.x_web import XWeb
            return XWeb()
        return [("X API (paid tier)", api), ("X browser session (free, experimental)", browser),
                ("X via web search index (free, no login, sample only)", web_index)]
    if pl == "youtube":
        def api():
            from .collectors.youtube import YouTubeCollector
            return YouTubeCollector(api_key=S.get("YOUTUBE_API_KEY"), max_videos=mv, max_comments=mc)

        def ytdlp():
            from .collectors.youtube_ytdlp import YtDlpYouTube
            return YtDlpYouTube(max_videos=mv, max_comments=min(mc, 100))
        return [("YouTube Data API", api), ("yt-dlp (no key)", ytdlp)]
    chans = [c.strip() for c in telegram_channels.split(",") if c.strip()]

    def tele():
        from .collectors.telegram import TelegramCollector
        if not _tg_api_ready():
            raise RuntimeError("Telegram API login not set up")
        return TelegramCollector(chans, api_id=S.get("TELEGRAM_API_ID"), api_hash=S.get("TELEGRAM_API_HASH"),
                                 session=S.telegram_session_path())

    def web():
        from .collectors.telegram_web import TelegramWeb
        return TelegramWeb(chans)
    return [("Telegram API (Telethon)", tele), ("Telegram web preview (no login)", web)]


def _run_chain(pl, topic, since, until, limit, telegram_channels, x_archive, depth, cancelled, log, notes):
    """Try each route in order; the first that completes wins (an empty but successful result is a valid answer).  Everything that goes wrong is written to the
    run notes, so the report shows exactly which route produced the data and why earlier ones were skipped."""
    tried = []
    # No channels + a Telegram login = global search, nothing to discover.  Without a login the web preview needs channels,
    # so web discovery runs (lazily, only if that route is actually reached).
    for label, factory in _chain(pl, telegram_channels, x_archive, depth):
        if pl == "telegram" and label.startswith("Telegram web") and not telegram_channels.strip():
            telegram_channels = _discover_channels(topic, since, until, log, notes)
            factory = dict(_chain(pl, telegram_channels, x_archive, depth))[label]
        try:
            c = factory()
        except RuntimeError as e:                                   # not configured -> next route
            tried.append(f"{label}: not configured ({e})")
            continue
        c.log, c.cancelled = log, cancelled
        try:
            log(f"{pl}: starting via {label}")
            got = c.collect(topic, since, until, limit)
        except Cancelled:
            raise
        except PlatformBlocked as e:
            tried.append(f"{label}: BLOCKED - {e}")
            log(f"{pl}: {label} blocked - {e}")
            continue
        except RuntimeError as e:
            tried.append(f"{label}: {e}")
            log(f"{pl}: {label} failed - {e}")
            continue
        except Exception as e:                                      # one bad route must not kill the run
            logging.exception("collector %s/%s failed", pl, label)
            tried.append(f"{label}: failed - {type(e).__name__}: {e}")
            log(f"{pl}: {label} failed - {type(e).__name__}: {e}")
            continue
        notes += [f"{pl}: {t}" for t in tried]
        notes += c.notes
        notes.append(f"{pl}: collected {len(got)} posts via {label}.")
        log(f"{pl}: {len(got)} posts via {label}")
        return got, label
    notes.append(f"{pl}: skipped - no route worked. " + " | ".join(tried))
    log(f"{pl}: skipped - " + " | ".join(tried))
    return [], None


def _discover_channels(topic, since, until, log, notes, max_channels: int = 8) -> str:
    """Telegram has no global search, so when the user named no channels, ask the free DuckDuckGo sweep which public
    channels mention the topic.  Best effort: if discovery finds nothing, Telegram is skipped with an explanatory note."""
    import tempfile
    from .discovery import discover
    try:
        log("telegram: no channels given - searching the web for public channels that mention the topic…")
        d = discover(topic, since, until, tempfile.mkdtemp(prefix="coordwatch-disc-"))
    except Exception as e:                                      # never fatal
        log(f"telegram: channel discovery failed ({type(e).__name__}: {e})")
        notes.append(f"telegram: channel discovery failed ({type(e).__name__}: {e})")
        return ""
    chans = [c["channel"] for c in d["telegram_channels"][:max_channels]]
    if chans:
        notes.append("telegram: channels found by web discovery (not chosen by you): " + ", ".join("@" + c for c in chans))
        log("telegram: discovered " + ", ".join(chans))
    else:
        qs = d["queries"]
        errs = [q["error"] for q in qs if not q.get("ok")]
        empty = sum(1 for q in qs if q.get("ok") and not q.get("n_results"))
        msg = (f"telegram: web discovery found no public channels ({len(qs)} searches: {empty} returned nothing, {len(errs)} errored"
               + (f"; first error: {errs[0][:140]}" if errs else "") + ")")
        log(msg)
        notes.append(msg + ". Enter channel names (e.g. @channel) in the Telegram box, or use a topic that appears on t.me.")
    return ",".join(chans)
