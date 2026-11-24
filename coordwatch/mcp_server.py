"""MCP server for coordwatch: lets Claude (Code, Desktop, or any MCP client) run an analysis and read the results.

Run (stdio, for Claude Code / Claude Desktop):   python -m coordwatch.mcp_server
Run (HTTP, bearer-token protected):              COORDWATCH_MCP_TOKEN=<long random secret> python -m coordwatch.mcp_server --http
    then connect a client to http://HOST:8765/mcp sending the header  Authorization: Bearer <secret>
    The server refuses to start in HTTP mode without a token (of at least 24 characters), and logs no token or post text.
Tools are narrow on purpose. Only `run_analysis` touches the network (through the existing collectors, with their
rate limiting); every other tool is read-only over a result held in memory. Post text is untrusted data: it comes
from public social media and may contain instructions aimed at an AI, so clients must never treat it as commands."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:                                   # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from .ai import answer_retrying, build_context
from .collect import LIVE, collect_posts
from .config import Config
from .pipeline import analyse

mcp = FastMCP("coordwatch")
_RUNS: Dict[str, dict] = {}          # run_id -> full result (in memory only; lost when the server stops)
MAX_RUNS = 10


def _get(run_id: str) -> dict:
    if run_id not in _RUNS:
        raise ValueError(f"Unknown run_id '{run_id}'. Known runs: {list(_RUNS) or 'none - call run_analysis first'}")
    return _RUNS[run_id]


@mcp.tool()
def run_analysis(topic: str, days: int = 7, platforms: Optional[List[str]] = None, demo: bool = False) -> dict:
    """Collect public posts about `topic` and analyse them for narratives and coordinated activity.
    days: look-back window (1-14). platforms: any of youtube, telegram, x (default all three). demo=True uses
    synthetic data with a planted ground truth (no network, no keys). Returns a run_id plus a short summary; use the
    other tools with that run_id to read details. Coordination is a clue, not proof."""
    days = max(1, min(14, int(days)))
    platforms = [] if demo else ([p for p in (platforms or list(LIVE)) if p in LIVE] or list(LIVE))
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    if demo:                          # the synthetic data has fixed dates (1-14 Oct 2026) and the topic 'Acme Bank'
        since, until, topic = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 15, tzinfo=timezone.utc), "Acme Bank"
    logs: List[str] = []
    posts, notes = collect_posts(topic, since, until, platforms, use_demo=demo, log=logs.append)
    res = analyse(posts, topic, since, until, None, Config(), notes, topic_filter=False)
    run_id = uuid.uuid4().hex[:8]
    _RUNS[run_id] = res
    while len(_RUNS) > MAX_RUNS:
        _RUNS.pop(next(iter(_RUNS)))
    m = res["meta"]
    return {"run_id": run_id, "posts": m["n_posts"], "accounts": m["n_accounts"], "platforms": m["platforms"],
            "narratives": m["n_narratives"], "coordinated_groups": m["n_groups"],
            "coordinated_accounts": m["coordinated_accounts"], "coordinated_post_share": m["coordinated_post_share"],
            "collector_notes": m["collector_notes"][:10]}


@mcp.tool()
def list_narratives(run_id: str, limit: int = 10) -> List[dict]:
    """The biggest stories in a run: id, title, size, platforms, share of posts from coordinated accounts."""
    res = _get(run_id)
    keep = ("id", "title", "size", "platforms", "coordinated_post_share")
    return [{k: n.get(k) for k in keep} for n in res["narratives"] if n["id"] >= 0][:max(1, min(50, limit))]


@mcp.tool()
def list_coordinated_groups(run_id: str) -> List[dict]:
    """Groups of accounts that appear to act together, with score, confidence and the evidence behind it."""
    res = _get(run_id)
    keep = ("id", "size", "score", "confidence", "accounts", "evidence", "narratives")
    return [{k: g.get(k) for k in keep if k in g} for g in res["coordinated_groups"]]


@mcp.tool()
def get_origins(run_id: str) -> object:
    """Earliest-found post per narrative. 'Earliest found' is not necessarily the true origin."""
    return _get(run_id)["origins"]


@mcp.tool()
def ask(run_id: str, question: str) -> str:
    """Ask a plain-language question about a run, answered by the AI provider configured in coordwatch settings,
    grounded only in this run's results. Fails with a clear message if no AI provider is configured."""
    res = _get(run_id)
    text, _model = answer_retrying(question, build_context(res))
    return text


class BearerAuth:
    """ASGI middleware: every HTTP request must carry 'Authorization: Bearer <token>' (constant-time comparison)."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            import hmac
            hdr = dict(scope.get("headers") or []).get(b"authorization", b"")
            given = hdr[7:] if hdr[:7].lower() == b"bearer " else b""
            if not hmac.compare_digest(given, self.token):
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401, "headers": [
                    (b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def serve_http(host: str = "0.0.0.0", port: int = 8765) -> None:
    import os
    import uvicorn
    token = os.environ.get("COORDWATCH_MCP_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("Set COORDWATCH_MCP_TOKEN to a random secret of at least 24 characters, e.g. "
                         "python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    uvicorn.run(BearerAuth(mcp.streamable_http_app(), token), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import sys
    serve_http() if "--http" in sys.argv else mcp.run()
