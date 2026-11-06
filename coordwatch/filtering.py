"""Topic / date / platform filtering applied to every source (live APIs are filtered server-side too,
but we re-check locally so results are consistent across platforms)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, List, Optional

from .models import Post


def topic_terms(topic: str) -> List[str]:
    """'Acme Bank OR #AcmeBankCollapse' -> ['acme bank', '#acmebankcollapse'].  Quotes are ignored."""
    parts = re.split(r"\s+OR\s+|\|", topic.replace('"', ""), flags=re.I)
    return [p.strip().lower() for p in parts if p.strip()]


def matches_topic(text: str, topic: str) -> bool:
    low = (text or "").lower()
    squashed = re.sub(r"\s+", "", low)
    for t in topic_terms(topic):
        if t in low or t.replace(" ", "") in squashed:  # "acme bank" also matches "#AcmeBank"
            return True
    return False


def filter_posts(posts: Iterable[Post], topic: str, since: Optional[datetime], until: Optional[datetime],
                 platforms: Optional[List[str]] = None) -> List[Post]:
    out, seen = [], set()
    for p in posts:
        if platforms and p.platform not in platforms:
            continue
        if since and p.created_at < since:
            continue
        if until and p.created_at > until:
            continue
        if not matches_topic(p.text, topic):
            continue
        key = (p.platform, p.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    out.sort(key=lambda p: p.created_at)
    return out
