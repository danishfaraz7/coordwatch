"""Cross-platform correlation: do the platforms talk about the same things, and who leads whom?

Everything here is descriptive and deterministic. A correlation is a lead for an analyst, not proof of coordination.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import timedelta
from itertools import combinations
from typing import Dict, List, Optional

from .models import Post
from .textutil import URL_RE

HASHTAG_RE = re.compile(r"#\w{3,}", re.UNICODE)
_YT_ID = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^\s#]*&)?v=|shorts/|embed/|live/))([\w-]{11})")
_TRACKING = re.compile(r"[?&](utm_\w+|fbclid|si|feature|t)=[^&\s]*")


def _norm_url(u: str) -> str:
    u = _TRACKING.sub("", u.strip().rstrip(".,;:!?)]}\"'")).lower()
    u = re.sub(r"^https?://(www\.|m\.)?", "", u)
    return u.rstrip("/?&")


def _pearson(a: List[float], b: List[float]) -> Optional[float]:
    n = len(a)
    if n < 4:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _series(posts: List[Post], plat: str, t0, size: timedelta, n: int) -> List[float]:
    s = [0.0] * n
    for p in posts:
        if p.platform == plat:
            i = int((p.created_at - t0) / size)
            if 0 <= i < n:
                s[i] += 1
    return s


def _lead_lag(a: List[float], b: List[float], max_lag: int = 3):
    """Best shift k (in buckets) such that b[t+k] tracks a[t]. k>0: b follows a."""
    best = (None, 0)
    for k in range(-max_lag, max_lag + 1):
        x = a[:len(a) - k] if k > 0 else a[-k:]
        y = b[k:] if k > 0 else b[:len(b) + k]
        r = _pearson(x, y)
        if r is not None and (best[0] is None or r > best[0]):
            best = (r, k)
    return best


def correlate(posts: List[Post], assign: List[int], narratives: List[dict], dup_clusters: List[dict], size: timedelta) -> dict:
    plats = sorted({p.platform for p in posts})
    out: Dict = {"platforms": plats, "available": len(plats) >= 2, "per_platform": {}, "narrative_overlap": [],
                 "volume_correlation": [], "shared_urls": [], "shared_hashtags": [], "youtube_links_in_telegram": [],
                 "cross_platform_copies": [], "same_name_accounts": [], "summary": []}
    for pl in plats:
        ps = [p for p in posts if p.platform == pl]
        out["per_platform"][pl] = {"posts": len(ps), "accounts": len({p.account for p in ps}),
                                   "engagement": sum(p.likes + p.shares + p.replies for p in ps),
                                   "first": min(p.created_at for p in ps).isoformat(), "last": max(p.created_at for p in ps).isoformat()}
    if not out["available"]:
        out["summary"] = [f"Only {plats[0] if plats else 'no platform'} returned posts, so no cross-platform comparison is possible. "
                          "Check the run log to see why the other platform(s) returned nothing."]
        return out

    # --- narratives that live on more than one platform
    for nar in narratives:
        nid = nar["id"]
        if nid < 0:
            continue
        idx = [i for i, a in enumerate(assign) if a == nid]
        by = Counter(posts[i].platform for i in idx)
        floor = max(2, round(0.1 * len(idx)))
        present = sorted(pl for pl, c in by.items() if c >= floor)
        if len(present) < 2:
            continue
        firsts = {}
        for i in sorted(idx, key=lambda i: posts[i].created_at):
            firsts.setdefault(posts[i].platform, posts[i])
        order = sorted(present, key=lambda pl: firsts[pl].created_at)
        lag = round((firsts[order[1]].created_at - firsts[order[0]].created_at).total_seconds() / 3600, 1)
        out["narrative_overlap"].append({"narrative_id": nid, "label": nar["label"], "posts": len(idx), "by_platform": dict(by),
                                         "first_platform": order[0], "then": order[1:], "lag_hours_to_next": lag})
    out["narrative_overlap"].sort(key=lambda o: -o["posts"])

    # --- volume correlation and lead/lag per platform pair
    t0 = min(p.created_at for p in posts)
    n = int((max(p.created_at for p in posts) - t0) / size) + 1
    unit = "hour" if size < timedelta(days=1) else "day"
    series = {pl: _series(posts, pl, t0, size, n) for pl in plats}
    for a, b in combinations(plats, 2):
        r0 = _pearson(series[a], series[b])
        rk, k = _lead_lag(series[a], series[b])
        row = {"a": a, "b": b, "buckets": n, "unit": unit, "r": None if r0 is None else round(r0, 2),
               "best_r": None if rk is None else round(rk, 2), "best_lag": k, "leader": None}
        if rk is not None and rk >= 0.5 and k != 0 and (r0 is None or rk - r0 >= 0.1):
            row["leader"] = a if k > 0 else b
        out["volume_correlation"].append(row)

    # --- shared artefacts
    urls, tags = defaultdict(set), defaultdict(set)
    for p in posts:
        for u in URL_RE.findall(p.text or ""):
            nu = _norm_url(u)
            if nu and "t.me/" not in nu:
                urls[nu].add(p.platform)
        for t in HASHTAG_RE.findall(p.text or ""):
            tags[t.lower()].add(p.platform)
    cnt = Counter(_norm_url(u) for p in posts for u in URL_RE.findall(p.text or ""))
    out["shared_urls"] = [{"url": u, "platforms": sorted(v), "posts": cnt[u]} for u, v in
                          sorted(urls.items(), key=lambda kv: -cnt[kv[0]]) if len(v) >= 2][:15]
    tcnt = Counter(t.lower() for p in posts for t in HASHTAG_RE.findall(p.text or ""))
    out["shared_hashtags"] = [{"tag": t, "platforms": sorted(v), "posts": tcnt[t]} for t, v in
                              sorted(tags.items(), key=lambda kv: -tcnt[kv[0]]) if len(v) >= 2][:15]

    # --- telegram posts that link to the YouTube videos we collected (the strongest YouTube<->Telegram tie)
    yt = {}
    for p in posts:
        if p.platform == "youtube":
            m = _YT_ID.search(p.url or "")
            if m:
                yt.setdefault(m.group(1), p)
    for p in sorted(posts, key=lambda p: p.created_at):
        if p.platform == "telegram":
            for vid in dict.fromkeys(_YT_ID.findall(p.text or "")):
                v = yt.get(vid)
                if v:
                    out["youtube_links_in_telegram"].append({
                        "video_id": vid, "video_url": v.url, "video_at": v.created_at.isoformat(), "telegram_post": p.url,
                        "telegram_account": p.account, "telegram_at": p.created_at.isoformat(),
                        "telegram_after_video_hours": round((p.created_at - v.created_at).total_seconds() / 3600, 1)})

    # --- near-identical text that appears on several platforms
    for c in dup_clusters:
        mem = sorted((posts[i] for i in c["posts"]), key=lambda p: p.created_at)
        pls = sorted({p.platform for p in mem})
        if len(pls) >= 2:
            out["cross_platform_copies"].append({"cluster": c["id"], "platforms": pls, "posts": len(mem),
                                                 "accounts": len({p.account for p in mem}), "first_platform": mem[0].platform,
                                                 "first_at": mem[0].created_at.isoformat(), "sample": (mem[0].text or "")[:160]})
    out["cross_platform_copies"].sort(key=lambda c: -c["posts"])

    # --- identical display names on different platforms (weak lead: names are not identities)
    names = defaultdict(set)
    for p in posts:
        k = re.sub(r"[^a-z0-9]", "", (p.author_name or "").lower().lstrip("@"))
        if len(k) >= 4:
            names[k].add((p.platform, p.account))
    for k, v in names.items():
        if len({pl for pl, _ in v}) >= 2:
            out["same_name_accounts"].append({"name": k, "accounts": sorted(a for _, a in v)})
    out["same_name_accounts"] = out["same_name_accounts"][:15]

    out["summary"] = _summarise(out)
    return out


def _summarise(x: dict) -> List[str]:
    s = []
    pp = x["per_platform"]
    s.append("Volume: " + ", ".join(f"{pl} {d['posts']} posts from {d['accounts']} accounts" for pl, d in pp.items()) + ".")
    ov = x["narrative_overlap"]
    if ov:
        top = ov[0]
        s.append(f"{len(ov)} narrative(s) appear on more than one platform. The largest, \"{top['label']}\", is on "
                 f"{', '.join(sorted(top['by_platform']))}; it surfaced first on {top['first_platform']} and reached "
                 f"{', '.join(top['then'])} about {abs(top['lag_hours_to_next'])} h later.")
        lead = Counter(o["first_platform"] for o in ov)
        pl, c = lead.most_common(1)[0]
        if len(ov) >= 3 and c / len(ov) >= 0.6:
            s.append(f"{pl} led in {c} of {len(ov)} shared narratives, so it looks like the usual upstream platform for this topic.")
    else:
        s.append("No narrative has meaningful volume on more than one platform: the platforms are discussing this topic separately.")
    for v in x["volume_correlation"]:
        if v["r"] is None:
            s.append(f"{v['a']} vs {v['b']}: too few {v['unit']}s with activity to correlate volume.")
        elif v["leader"]:
            fol = v["b"] if v["leader"] == v["a"] else v["a"]
            s.append(f"{v['a']} vs {v['b']}: volumes correlate at r={v['best_r']} when {fol} is shifted by {abs(v['best_lag'])} {v['unit']}(s), "
                     f"i.e. {v['leader']} moves first.")
        else:
            strength = "strongly" if v["r"] >= 0.7 else "moderately" if v["r"] >= 0.4 else "weakly or not at all"
            s.append(f"{v['a']} vs {v['b']}: {'hourly' if v['unit'] == 'hour' else 'daily'} volume correlates {strength} (r={v['r']}) with no clear leader.")
    if x["youtube_links_in_telegram"]:
        L = x["youtube_links_in_telegram"]
        s.append(f"{len(L)} Telegram post(s) link to YouTube videos in this dataset (strongest cross-platform tie); "
                 f"the earliest shared a video {L[0]['telegram_after_video_hours']} h after it was published.")
    if x["cross_platform_copies"]:
        c = x["cross_platform_copies"][0]
        s.append(f"{len(x['cross_platform_copies'])} near-identical text cluster(s) span platforms; the largest has {c['posts']} posts from "
                 f"{c['accounts']} accounts and first appeared on {c['first_platform']}.")
    if x["shared_urls"]:
        s.append(f"{len(x['shared_urls'])} URL(s) are shared on several platforms, e.g. {x['shared_urls'][0]['url'][:80]}.")
    if x["same_name_accounts"]:
        s.append(f"{len(x['same_name_accounts'])} display name(s) occur on several platforms; treat as a lead only, names are not identities.")
    s.append("These are correlations in public data, not proof of coordination or common control.")
    return s
