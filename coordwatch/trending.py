"""'What is trending' suggestions for the search box. Free, no keys, best effort.

Sources (each fails on its own, never the whole call):
  web       Google Trends daily RSS (what people search right now) + Google News top stories + GDELT news for the chosen dates
  youtube   popular videos about the top web topics (YouTube has no public trending list any more), read with yt-dlp if installed
  telegram  hashtags and phrases in the recent posts of the public channels you list (t.me/s preview)
Every source returns plain terms the user can add to the search with one click.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

_UA = "Mozilla/5.0 (X11; Linux x86_64) coordwatch-trending"
STOP = set("""a an the and or of to in on for with at by from is are was were be been it its this that these those as but not no
you your we our they their he she his her i me my will would can could should may might do does did have has had about after before
over under into than then so if how what when where who why which new news live video watch full today latest says say said vs""".split())
_TAG = re.compile(r"#\w{2,40}", re.U)
_CAP = re.compile(r"\b(?:[A-Z][\w'’.-]+)(?:\s+(?:vs\.?|v|of|de|and|&|[A-Z][\w'’.-]+)){0,3}")


def _get(url: str, timeout: int = 12) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
    r.raise_for_status()
    return r.text


def terms_from(texts: List[tuple], top: int = 12) -> List[dict]:
    """texts = [(text, weight)]. Hashtags and capitalised phrases, scored by weight, with one example."""
    score, example = Counter(), {}
    for text, w in texts:
        found = set(t.lower() for t in _TAG.findall(text))
        for m in _CAP.findall(text):
            m = re.sub(r"\s+", " ", m).strip(" .-&")
            words = m.split()
            if not words or len(m) < 4 or all(x.lower() in STOP for x in words) or (len(words) == 1 and words[0].lower() in STOP):
                continue
            found.add(m)
        for t in found:
            key = t.lower()
            score[key] += w
            example.setdefault(key, (t if t.startswith("#") else t, text.strip()[:110]))
    out, seen = [], []
    for key, sc in score.most_common(80):
        if any(key != o and (key in o or o in key) for o in seen):        # drop "India" when "India vs New Zealand" is already there
            continue
        seen.append(key)
        out.append({"term": example[key][0], "score": round(sc), "example": example[key][1]})
        if len(out) >= top:
            break
    return out


def web_source(since: datetime, until: datetime, geo: str, get: Callable[[str], str]) -> dict:
    items, notes = [], []
    try:
        root = ET.fromstring(get(f"https://trends.google.com/trending/rss?geo={geo}"))
        ns = {"ht": "https://trends.google.com/trending/rss"}
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            tr = (it.findtext("ht:approx_traffic", namespaces=ns) or "").replace("+", "").replace(",", "")
            if t:
                items.append({"term": t, "score": int(tr) if tr.isdigit() else 0, "example": "Searched a lot on Google right now"})
    except Exception as e:
        notes.append(f"Google Trends unavailable ({type(e).__name__})")
    heads = []
    try:
        root = ET.fromstring(get(f"https://news.google.com/rss?hl=en-{geo}&gl={geo}&ceid={geo}:en"))
        heads = [(i.findtext("title") or "", 1) for i in root.iter("item")]
    except Exception as e:
        notes.append(f"Google News unavailable ({type(e).__name__})")
    try:
        import json
        f = "%Y%m%d%H%M%S"
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + "(india OR world OR trending) sourcelang:english".replace(" ", "%20") +
               f"&mode=artlist&format=json&maxrecords=250&sort=hybridrel&startdatetime={since.strftime(f)}&enddatetime={until.strftime(f)}")
        heads += [(a.get("title", ""), 1) for a in json.loads(get(url)).get("articles", [])]
    except Exception as e:
        notes.append(f"GDELT unavailable ({type(e).__name__})")
    items += terms_from(heads, 12)
    note = "Google Trends shows today; the news terms follow your dates." + ((" " + "; ".join(notes)) if notes else "")
    return {"id": "web", "label": "Open internet", "items": items[:20], "note": note, "headlines": heads}


def youtube_source(web_items: List[dict], search: Optional[Callable[[str], List[dict]]] = None) -> dict:
    note = "YouTube has no public trending list, so this shows popular videos about today's top web topics."
    search = search or _yt_search
    texts = []
    try:
        for it in web_items[:3]:
            for v in search(it["term"]):
                texts.append((v.get("title") or "", max(1, int(v.get("view_count") or 1))))
    except Exception as e:
        return {"id": "youtube", "label": "YouTube", "items": [], "note": f"Could not read YouTube here ({type(e).__name__}: install yt-dlp and check your internet)."}
    return {"id": "youtube", "label": "YouTube", "items": terms_from(texts, 12), "note": note}


def _yt_search(term: str) -> List[dict]:
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True, "socket_timeout": 12}) as y:
        return (y.extract_info(f"ytsearch10:{term}", download=False) or {}).get("entries", [])


def telegram_source(channels: List[str], since: datetime, until: datetime, get: Callable[[str], str]) -> dict:
    chans = [c.strip().lstrip("@").replace("https://t.me/", "").strip("/") for c in channels if c.strip()]
    if not chans:
        return {"id": "telegram", "label": "Telegram", "items": [], "note": "Type some public channels in the Telegram box (for example @bbcnews) and press the button again."}
    from .collectors.telegram_web import parse_page
    texts, errs = [], []
    for ch in chans[:8]:
        try:
            for p in parse_page(get(f"https://t.me/s/{ch}"), ch):
                if p.text and (not p.created_at or since <= p.created_at.replace(tzinfo=p.created_at.tzinfo or timezone.utc) <= until + timedelta(days=1)):
                    texts.append((p.text, max(1, int(p.views or 1))))
        except Exception as e:
            errs.append(f"{ch}: {type(e).__name__}")
    note = "From the latest posts of the channels you listed." + (" Problems: " + ", ".join(errs) if errs else "")
    return {"id": "telegram", "label": "Telegram", "items": terms_from(texts, 12), "note": note}


def trending(since: datetime, until: datetime, geo: str = "IN", channels: Optional[List[str]] = None, platforms=("web", "youtube", "telegram"),
             get: Callable[[str], str] = _get, yt_search=None) -> Dict:
    geo = (geo or "IN").upper()[:2]
    since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    until = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
    srcs, web = [], {"items": []}
    if "web" in platforms or "youtube" in platforms:
        web = web_source(since, until, geo, get)
        if "web" in platforms:
            srcs.append({k: v for k, v in web.items() if k != "headlines"})
    if "youtube" in platforms:
        srcs.append(youtube_source(web["items"], yt_search))
    if "telegram" in platforms:
        srcs.append(telegram_source(channels or [], since, until, get))
    return {"since": since.date().isoformat(), "until": until.date().isoformat(), "sources": srcs}
