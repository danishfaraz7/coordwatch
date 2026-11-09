"""App activity log: every lookup made inside the app (searches, AI summaries, trending lookups, downloads).

One JSON line per event in <home>/activity.jsonl.  Secret-free by construction: only what the user typed, counts, timings,
provider/model names and error text are stored - never keys, tokens or the full context sent to an AI (only its size).
The text is merged into Settings -> Run logs, so one export shows both the runs and what was done with them."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Optional, Tuple

from . import secrets_store as S

_LOCK = threading.Lock()
MAX_BYTES = 5_000_000


def _path():
    return S.home() / "activity.jsonl"


def record(kind: str, **fields) -> None:
    """Append one event. Never raises - logging must not break a lookup."""
    try:
        ev = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind}
        for k, v in fields.items():
            if v is None:
                continue
            ev[k] = v[:1500] if isinstance(v, str) else v
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            if p.exists() and p.stat().st_size > MAX_BYTES:                  # keep the newest half
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                p.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _fmt(ev: dict) -> str:
    t = ev.get("t", "")[:19].replace("T", " ")
    rest = {k: v for k, v in ev.items() if k not in ("t", "kind")}
    body = "  ".join(f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (str, list, dict)) else v}" for k, v in rest.items())
    return f"{t} UTC  {ev.get('kind', '?'):<9} {body}"


def collect(start: datetime, end: datetime) -> Tuple[str, int]:
    """Text block of the events between start and end (inclusive) and how many there were."""
    out = []
    try:
        for line in _path().read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
                t = datetime.fromisoformat(ev["t"])
            except Exception:
                continue
            if start <= t <= end:
                out.append(_fmt(ev))
    except FileNotFoundError:
        pass
    if not out:
        return "", 0
    head = "coordwatch app activity log\n" + "=" * 60 + "\n(searches, AI summaries, trending lookups and downloads made in the app; no keys or tokens)\n\n"
    return head + "\n".join(out), len(out)


def for_run(run_id: str) -> str:
    """Events that mention one run (for the end of its run_log.txt when it is rewritten)."""
    out = []
    try:
        for line in _path().read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("run") == run_id:
                out.append(_fmt(ev))
    except FileNotFoundError:
        pass
    return "\n".join(out)
