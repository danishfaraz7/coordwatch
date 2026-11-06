"""Lightweight 'is this credential working?' checks for the Settings screen.
Each returns {service, state, message}; state is one of:
  connected | invalid | limited (key accepted but quota/billing/access is missing) | unverified | unreachable | unset
Nothing here sends user data; the calls are cheap metadata endpoints."""
from __future__ import annotations

from typing import Callable, Optional

from . import ai
from . import secrets_store as S


def _res(service: str, state: str, message: str) -> dict:
    return {"service": service, "state": state, "message": message}


def validate(service: str, get: Optional[Callable] = None) -> dict:
    import requests
    get = get or requests.get
    try:
        if service == "youtube":
            return _youtube(get)
        if service == "gemini":
            return _gemini(get)
        if service == "x":
            return _x(get)
        if service == "telegram":
            return _telegram()
    except Exception as e:                                   # network / proxy / DNS - never leak details like URLs with keys
        return _res(service, "unreachable", f"Could not reach the service ({type(e).__name__}). Check your internet connection or proxy.")
    return _res(service, "invalid", "Unknown service.")


def _youtube(get) -> dict:
    key = S.get("YOUTUBE_API_KEY")
    if not key:
        return _res("youtube", "unset", "No API key saved.")
    r = get("https://www.googleapis.com/youtube/v3/videoCategories", params={"part": "snippet", "regionCode": "US", "key": key}, timeout=15)
    if r.status_code == 200:
        return _res("youtube", "connected", "Key accepted - YouTube Data API reachable.")
    try:
        reason = (r.json().get("error", {}).get("errors") or [{}])[0].get("reason", "")
    except Exception:
        reason = ""
    if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
        return _res("youtube", "limited", "Key is valid but today's quota is used up (resets daily).")
    if reason in ("accessNotConfigured", "forbidden", "ipRefererBlocked") or r.status_code == 403:
        return _res("youtube", "limited", "Key exists but cannot use the API: enable 'YouTube Data API v3' for its project.")
    return _res("youtube", "invalid", "Google rejected this API key.")


def _gemini(get) -> dict:
    key = S.get("GEMINI_API_KEY")
    if not key:
        return _res("gemini", "unset", "No API key saved (optional).")
    r = get(f"{ai.API}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=15)
    if r.status_code == 200:
        model = ai.pick_model(r.json().get("models", [])) or ai.FALLBACK_MODEL
        return _res("gemini", "connected", f"Key accepted - will use model {model}.")
    if r.status_code == 429:
        return _res("gemini", "limited", "Key accepted, but the free-tier rate limit is hit right now.")
    return _res("gemini", "invalid", "Google rejected this API key.")


def _x(get) -> dict:
    tok = S.get("X_BEARER_TOKEN")
    if not tok:
        return _res("x", "unset", "No bearer token saved.")
    r = get("https://api.x.com/2/usage/tweets", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    if r.status_code == 200:
        return _res("x", "connected", "Token accepted. (Searching still uses paid credits.)")
    if r.status_code == 401:
        return _res("x", "invalid", "X rejected this bearer token.")
    if r.status_code in (402, 403, 429):
        return _res("x", "limited", f"X answered HTTP {r.status_code}: the token may be fine but this app lacks access or credits.")
    return _res("x", "unverified", f"X answered HTTP {r.status_code}; could not confirm.")


def _telegram() -> dict:
    have = S.get("TELEGRAM_API_ID") and S.get("TELEGRAM_API_HASH")
    if not have:
        return _res("telegram", "unset", "api_id / api_hash not saved.")
    if not S.telegram_logged_in():
        return _res("telegram", "limited", "Keys saved, but no login session yet - run: python -m coordwatch telegram-login")
    return _res("telegram", "unverified", "Keys saved and a login session exists (not network-tested here).")
