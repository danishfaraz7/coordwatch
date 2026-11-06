"""Where API credentials live.  Priority: environment variable (e.g. Codespaces secret) > ~/.coordwatch/credentials.json.
The file is outside the repository so it cannot be committed by accident; values are never returned to the browser."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

KEYS = ["X_BEARER_TOKEN", "YOUTUBE_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "GEMINI_API_KEY"]


def home() -> Path:
    p = Path(os.environ.get("COORDWATCH_HOME") or (Path.home() / ".coordwatch"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _file() -> Path:
    return home() / "credentials.json"


def _load() -> Dict[str, str]:
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def get(name: str) -> Optional[str]:
    return os.environ.get(name) or _load().get(name) or None


def status() -> Dict[str, dict]:
    f = _load()
    return {k: {"set": bool(os.environ.get(k) or f.get(k)), "source": "env" if os.environ.get(k) else ("file" if f.get(k) else None)}
            for k in KEYS}


def save(updates: Dict[str, Optional[str]]) -> None:
    data = _load()
    for k, v in updates.items():
        if k not in KEYS:
            continue
        v = (v or "").strip()
        if v:
            data[k] = v
        else:
            data.pop(k, None)
    fd = os.open(_file(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # owner read/write only (POSIX)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def telegram_session_path() -> str:
    return str(home() / "telegram")      # Telethon appends ".session"


def telegram_logged_in() -> bool:
    return (home() / "telegram.session").exists()
