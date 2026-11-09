"""Build a report-ready result for a chosen set of stories (one, several or all) without re-clustering,
so Story numbers stay exactly as they were in the app."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Iterable

from .crossplatform import correlate
from .models import Post, parse_dt
from .narratives import bucket_size, bucket_start
from .overview import build as build_overview


def subset(result: dict, ids: Iterable[int]) -> dict:
    want = {int(i) for i in ids}
    have = {n["id"] for n in result["narratives"] if n["id"] >= 0}
    want &= have
    if not want:
        raise ValueError("Pick at least one story.")
    rows = [r for r in result["posts"] if r["narrative_id"] in want]
    posts = [Post.from_dict({k: v for k, v in r.items() if k not in ("narrative_id", "coordinated_group")}) for r in rows]
    assign = [r["narrative_id"] for r in rows]
    nars = [dict(n) for n in result["narratives"] if n["id"] in want]
    acct_in = {p.account for p in posts}
    groups = []
    for g in result["coordinated_groups"]:
        sel = {k: v for k, v in (g.get("narratives") or {}).items() if int(k) in want}
        accts = [a for a in g["accounts"] if a in acct_in]
        if not sel or not accts:
            continue
        g2 = dict(g)
        g2.update(narratives=sel, accounts=accts, size=len(accts), posts=sum(1 for p in posts if p.account in set(accts)))
        groups.append(g2)
    acct_group = {a: g["id"] for g in groups for a in g["accounts"]}
    for r in rows:
        r["coordinated_group"] = acct_group.get(r["account"])
    origins = [o for o in result["origins"] if o["narrative_id"] in want]
    m = dict(result["meta"])
    size = bucket_size(posts)
    vol = Counter(bucket_start(p.created_at, size).isoformat() for p in posts)
    vol_pl = defaultdict(Counter)
    for p in posts:
        vol_pl[p.platform][bucket_start(p.created_at, size).isoformat()] += 1
    m.update(n_posts=len(posts), n_accounts=len(acct_in), n_narratives=len(nars), n_groups=len(groups), coordinated_accounts=len(acct_group),
             coordinated_post_share=round(sum(1 for p in posts if p.account in acct_group) / max(len(posts), 1), 3),
             platforms=sorted({p.platform for p in posts}), bucket="hour" if size < timedelta(days=1) else "day",
             selection={"stories": sorted(want), "of": len(have)})
    out = dict(result)
    out.update(meta=m, posts=rows, narratives=nars, coordinated_groups=groups, origins=origins,
               volume={"total": dict(sorted(vol.items())), "by_platform": {k: dict(sorted(v.items())) for k, v in vol_pl.items()}},
               cross_platform=correlate(posts, assign, nars, [], size),
               overview=build_overview(posts, assign, nars, groups, origins, m["topic"], parse_dt(m["since"]), parse_dt(m["until"])))
    return out
