"""End-to-end orchestration: filter -> narratives -> coordination -> origins -> result dict."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from .config import Config
from .coordination import detect
from .filtering import filter_posts
from .models import Post
from .narratives import analyse_narratives, bucket_size, bucket_start
from .origin import trace_origins


def analyse(all_posts: List[Post], topic: str, since: Optional[datetime], until: Optional[datetime],
            platforms: Optional[List[str]] = None, cfg: Optional[Config] = None, collector_notes=None) -> dict:
    cfg = cfg or Config()
    posts = filter_posts(all_posts, topic, since, until, platforms)
    if not posts:
        raise SystemExit("No posts matched the topic / date range / platforms. Check the inputs.")
    narratives, assign, vecs = analyse_narratives(posts, topic, cfg)
    coord = detect(posts, vecs, cfg, assign)
    groups = coord["groups"]
    origins = trace_origins(posts, assign, narratives, groups, coord["dup_clusters"])

    acct_group = {a: g["id"] for g in groups for a in g["accounts"]}
    for nar in narratives:
        mem = [p for i, p in enumerate(posts) if assign[i] == nar["id"]]
        coord_posts = [p for p in mem if p.account in acct_group]
        nar["coordinated_post_share"] = round(len(coord_posts) / len(mem), 3) if mem else 0
        nar["coordinated_groups"] = dict(Counter(acct_group[p.account] for p in coord_posts))
    for g in groups:
        c = Counter(assign[i] for i, p in enumerate(posts) if p.account in set(g["accounts"]))
        g["narratives"] = {str(k): v for k, v in c.most_common() if k >= 0}
        g.pop("_post_ids", None)

    post_rows = []
    for i, p in enumerate(posts):
        d = p.to_dict()
        d["narrative_id"] = assign[i]
        d["coordinated_group"] = acct_group.get(p.account)
        post_rows.append(d)

    size = bucket_size(posts)
    vol = Counter(bucket_start(p.created_at, size).isoformat() for p in posts)
    vol_pl = defaultdict(Counter)
    for p in posts:
        vol_pl[p.platform][bucket_start(p.created_at, size).isoformat()] += 1

    return {
        "meta": {
            "topic": topic, "since": since.isoformat() if since else None, "until": until.isoformat() if until else None,
            "platforms": sorted({p.platform for p in posts}), "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_posts": len(posts), "n_accounts": len({p.account for p in posts}),
            "n_narratives": sum(1 for n in narratives if n["id"] >= 0), "n_groups": len(groups),
            "coordinated_accounts": len(acct_group),
            "coordinated_post_share": round(sum(1 for p in posts if p.account in acct_group) / len(posts), 3),
            "bucket": "hour" if size.days < 1 else "day", "config": cfg.to_dict(),
            "collector_notes": collector_notes or [],
        },
        "volume": {"total": dict(sorted(vol.items())),
                   "by_platform": {k: dict(sorted(v.items())) for k, v in vol_pl.items()}},
        "narratives": narratives, "coordinated_groups": groups, "origins": origins, "posts": post_rows,
    }
