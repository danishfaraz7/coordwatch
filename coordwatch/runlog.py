"""Plain-text run log: what was asked, what ran, what happened - one block you can paste into a chat or a ticket.

Contains NO secrets: credentials appear only as 'set' / 'not set'.  Everything the user typed (topic, dates, channels) is
included on purpose, because that is what you need to reproduce or tune a run."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from . import __version__
from . import secrets_store as S


def _commit() -> str:
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _iso(x) -> str:
    return x.strftime("%Y-%m-%d %H:%M UTC") if isinstance(x, datetime) else str(x)


def _credentials() -> List[str]:
    st = S.status()
    return [f"{k}: {'set (' + (v['source'] or '?') + ')' if v['set'] else 'not set'}"
            for k, v in st.items() if k in ("YOUTUBE_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "X_BEARER_TOKEN", "X_COOKIES_FILE")] \
        + [f"Telegram login: {'done' if S.telegram_logged_in() else 'not done'}"]


def build(params: dict, status: str, error: Optional[str], logs: Iterable[str], result: Optional[dict] = None,
          started: Optional[datetime] = None, ended: Optional[datetime] = None, notes: Optional[List[str]] = None) -> str:
    started = started or datetime.now(timezone.utc)
    ended = ended or datetime.now(timezone.utc)
    L: List[str] = ["coordwatch run log", "=" * 60]
    L.append(f"status      : {status.upper()}")
    L.append(f"started     : {_iso(started)}    duration: {(ended - started).total_seconds():.0f}s")
    L.append(f"version     : coordwatch {__version__} (git {_commit()})  python {sys.version.split()[0]}  {platform.system()}"
             + ("  [GitHub Codespaces]" if os.environ.get("CODESPACES") else ""))
    L += ["", "REQUEST", "-" * 60]
    L.append(f"topic       : {params.get('topic')}")
    L.append(f"date range  : {_iso(params.get('since'))} -> {_iso(params.get('until'))}")
    L.append(f"platforms   : {', '.join(params.get('platforms') or []) or '(none - demo/file only)'}")
    L.append(f"depth/limit : {params.get('depth', '-')} / {params.get('limit', '-')} posts per platform")
    L.append(f"tg channels : {params.get('telegram_channels') or '(none given)'}")
    L.append(f"mode        : {'DEMO (synthetic data)' if params.get('demo') else 'live/file'}"
             + (f"; uploads: {len(params.get('upload_ids') or [])}" if params.get("upload_ids") else ""))
    L.append("credentials : " + "; ".join(_credentials()))
    L += ["", "OUTCOME", "-" * 60]
    if result:
        m = result["meta"]
        per = {}
        for p in result["posts"]:
            per[p["platform"]] = per.get(p["platform"], 0) + 1
        L.append(f"posts       : {m['n_posts']} from {m['n_accounts']} accounts  (per platform: "
                 + (", ".join(f"{k} {v}" for k, v in sorted(per.items())) or "none") + ")")
        L.append(f"narratives  : {m['n_narratives']}")
        L.append(f"coordinated : {m['n_groups']} group(s), {m['coordinated_accounts']} accounts, "
                 f"{m['coordinated_post_share']:.0%} of posts")
        for g in result["coordinated_groups"][:6]:
            L.append(f"  {g['id']} [{g['confidence']} {g['score']}] {g['size']} accounts: " + " | ".join(g["reasons"][:2]))
    else:
        L.append("posts       : 0 (no result produced)")
    if error:
        L.append(f"error       : {error}")
    nts = notes if notes is not None else (result["meta"].get("collector_notes", []) if result else [])
    if nts:
        L += ["", "COLLECTOR NOTES (which route produced the data, what was skipped or blocked, limitations)", "-" * 60]
        L += [f"- {n}" for n in nts]
    logs = list(logs)
    if logs:
        L += ["", "TIMELINE", "-" * 60] + logs
    return "\n".join(L) + "\n"
