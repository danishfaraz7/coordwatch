"""Optional AI story names: replaces keyword labels such as "insolvent / withdraw / savings / too" with short human titles.
Best effort and opt-in: only a few short snippets per story go to the configured AI provider; any failure keeps the keyword labels."""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, Optional

MAX_STORIES = 12
_SKIP = re.compile(r"[<>\x00-\x1f]")

QUESTION = ("For each story write (1) a short, original, plain-English title of 3 to 7 words that says what the story is about, in your own words "
            "(never copy a post's headline; for example 'Rumour that the bank is insolvent') and (2) a clear summary of 3 to 4 sentences for an executive: "
            "what is being claimed or discussed, who is saying it and on which platforms, when it peaked, and whether it looks organic or coordinated. "
            "Use only the data and never invent facts. This task overrides the word limit and citation rule: reply with ONLY a JSON object mapping the story id "
            "(as a string) to {\"title\": ..., \"summary\": ...}, nothing else.")


def build_context(result: dict, max_stories: int = MAX_STORIES, per_story: int = 3) -> str:
    by_id = {p["id"]: p for p in result["posts"]}
    out = []
    for n in [x for x in result["narratives"] if x["id"] >= 0][:max_stories]:
        quotes = []
        for pid in (n.get("representative_posts") or [])[:per_story]:
            p = by_id.get(pid)
            if p:
                quotes.append(" ".join((p["text"] or "").split())[:200])
        out.append({"id": n["id"], "keywords": n.get("keywords", [])[:6], "posts": n["posts"], "accounts": n.get("accounts"), "platforms": n.get("platforms"),
                    "first_seen": (n.get("first_seen") or "")[:10], "last_seen": (n.get("last_seen") or "")[:10], "coordinated_share": round(n.get("coordinated_post_share", 0), 2),
                    "example_posts": quotes})
    return json.dumps({"stories": out}, ensure_ascii=False)


def parse_titles(text: str) -> Dict[int, dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        raw = json.loads(m.group(0))
    except Exception:
        return {}
    titles = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        try:
            i = int(re.sub(r"\D", "", str(k)))
        except ValueError:
            continue
        summ = ""
        if isinstance(v, dict):
            summ = _SKIP.sub("", re.sub(r"\[\d+\]", "", str(v.get("summary", "")))).strip()[:900]
            v = v.get("title", "")
        t = _SKIP.sub("", re.sub(r"\[\d+\]", "", str(v))).strip(" .\"'")
        if 3 <= len(t) <= 80:
            titles[i] = {"title": t, "summary": summ}
    return titles


def apply(result: dict, titles: Dict[int, dict]) -> int:
    """Swap the label of each named story everywhere it appears. The keyword label stays in `keyword_label`."""
    titles = {k: (v if isinstance(v, dict) else {"title": v, "summary": ""}) for k, v in titles.items()}
    old = {}
    for n in result["narratives"]:
        if n["id"] in titles:
            old[n["id"]] = n["label"]
            t = titles[n["id"]]
            n["keyword_label"], n["label"], n["headline"] = n["label"], t["title"], t["title"]
            if t["summary"]:
                n["summary"] = t["summary"]
    if not old:
        return 0
    swaps = {old[i]: titles[i]["title"] for i in old}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "label" and isinstance(v, str) and v in swaps and "narrative_id" in x:
                    x[k] = swaps[v]
                else:
                    x[k] = walk(v)
            return x
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, str):
            for a, b in swaps.items():
                if a in x:
                    x = x.replace(a, b)
        return x
    for key in ("origins", "cross_platform", "overview", "discovery"):
        if key in result and result[key] is not None:
            result[key] = walk(result[key])
    for n in (result.get("overview") or {}).get("narratives", []):
        if n.get("id") in titles:
            n["label"] = n["headline"] = titles[n["id"]]["title"]
    return len(old)


def name_stories(result: dict, cfg: dict, answer: Optional[Callable] = None, on_wait: Optional[Callable] = None) -> int:
    from . import ai
    if answer:
        text, _model = answer(QUESTION, build_context(result), cfg)
    else:
        text, _model = ai.answer_retrying(QUESTION, build_context(result), cfg, on_wait=on_wait)
    return apply(result, parse_titles(text))
