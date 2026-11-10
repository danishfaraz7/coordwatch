"""Common data model shared by every collector and analysis stage."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO strings / epoch seconds / epoch ms into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace(".", "", 1).isdigit()):
        x = float(value)
        if x > 1e11:  # milliseconds
            x /= 1000.0
        return datetime.fromtimestamp(x, tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%a %b %d %H:%M:%S %z %Y", "%d/%m/%Y %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Post:
    id: str                       # unique within platform
    platform: str
    author_id: str
    author_name: str
    text: str
    created_at: datetime
    url: str = ""
    likes: int = 0
    shares: int = 0
    replies: int = 0
    views: Optional[int] = None
    media: list = field(default_factory=list)     # [{"type": "photo|video", "url": str}]
    # account-level metadata (None when the platform does not expose it)
    author_created: Optional[datetime] = None
    author_followers: Optional[int] = None
    author_verified: bool = False
    avatar_hash: Optional[str] = None             # 64-bit perceptual hash, hex
    avatar_is_default: bool = False
    # relations
    is_reshare: bool = False                      # pure repost / forward (no new content)
    reshare_of: Optional[str] = None              # post id on same platform
    reshare_of_author: Optional[str] = None       # author_id of the original poster
    reply_to: Optional[str] = None
    lang: Optional[str] = None
    joined: Optional[bool] = None                 # Telegram only: True if the account is a member of the channel

    @property
    def account(self) -> str:
        return f"{self.platform}:{self.author_id}"

    @property
    def engagement(self) -> int:
        return int(self.likes or 0) + int(self.shares or 0) + int(self.replies or 0)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("created_at", "author_created"):
            d[k] = d[k].isoformat() if d[k] else None
        d["account"] = self.account
        d["engagement"] = self.engagement
        return d

    @staticmethod
    def from_dict(d: dict) -> "Post":
        d = dict(d)
        d.pop("account", None)
        d.pop("engagement", None)
        d["created_at"] = parse_dt(d["created_at"])
        d["author_created"] = parse_dt(d.get("author_created"))
        d["id"] = str(d["id"])
        d["author_id"] = str(d["author_id"])
        return Post(**d)
