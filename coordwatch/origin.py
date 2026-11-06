"""Narrative origin + cross-platform spread tracing."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from .models import Post


def trace_origins(posts: List[Post], assign: List[int], narratives: List[dict], groups: List[dict],
                  dup_clusters: List[dict]) -> List[dict]:
    acct_group = {a: g["id"] for g in groups for a in g["accounts"]}
    dup_post_cluster = {i: c["id"] for c in dup_clusters for i in c["posts"]}
    out = []
    for nar in narratives:
        nid = nar["id"]
        if nid < 0:
            continue
        idxs = sorted((i for i, a in enumerate(assign) if a == nid), key=lambda i: posts[i].created_at)
        ps = [posts[i] for i in idxs]
        t0 = ps[0].created_at

        def brief(p: Post) -> dict:
            return {"post_id": p.id, "account": p.account, "name": p.author_name, "platform": p.platform,
                    "at": p.created_at.isoformat(), "url": p.url, "text": p.text,
                    "coordinated_group": acct_group.get(p.account),
                    "minutes_after_origin": round((p.created_at - t0).total_seconds() / 60, 1)}

        first_accounts, seen = [], set()
        for p in ps:
            if p.account not in seen:
                seen.add(p.account)
                first_accounts.append(brief(p))
            if len(first_accounts) >= 5:
                break

        platform_first: Dict[str, dict] = {}
        for p in ps:
            platform_first.setdefault(p.platform, brief(p))
        spread = [{"platform": pl, "first_post": b["post_id"], "first_account": b["account"], "at": b["at"],
                   "lag_minutes": b["minutes_after_origin"]} for pl, b in platform_first.items()]

        # copy-paste lineage: the biggest duplicated text inside this narrative, first appearance per platform
        lineage = []
        counts = Counter(dup_post_cluster[i] for i in idxs if i in dup_post_cluster)
        if counts:
            cid, _ = counts.most_common(1)[0]
            mem = sorted((posts[i] for i in idxs if dup_post_cluster.get(i) == cid), key=lambda p: p.created_at)
            first_by_pl = {}
            for p in mem:
                first_by_pl.setdefault(p.platform, p)
            lineage = [{"platform": pl, "account": p.account, "at": p.created_at.isoformat(), "url": p.url,
                        "lag_minutes": round((p.created_at - mem[0].created_at).total_seconds() / 60, 1)}
                       for pl, p in first_by_pl.items()]

        k = max(5, len(ps) // 10)
        early = ps[:k]
        early_grp = Counter(acct_group[p.account] for p in early if p.account in acct_group)
        coord_share = sum(1 for p in early if p.account in acct_group) / len(early)
        seeding = early_grp.most_common(1)[0][0] if early_grp and coord_share >= 0.5 else None

        horizon = [p for p in ps if (p.created_at - t0).total_seconds() <= 48 * 3600]
        cascade = defaultdict(Counter)
        for p in horizon:
            cascade[int((p.created_at - t0).total_seconds() // 3600)][p.platform] += 1

        if seeding:
            verdict = (f"Likely seeded: {coord_share:.0%} of the first {len(early)} posts came from coordinated "
                       f"group {seeding}.")
        elif coord_share > 0:
            verdict = f"Mixed: {coord_share:.0%} of the first {len(early)} posts came from coordinated accounts."
        else:
            verdict = "No coordinated accounts among the earliest posts (looks organic)."
        out.append({
            "narrative_id": nid, "label": nar["label"], "first_post": brief(ps[0]),
            "first_accounts": first_accounts, "platform_spread": spread,
            "copy_paste_lineage": lineage, "early_wave_size": len(early),
            "early_wave_coordinated_share": round(coord_share, 3), "seeding_group": seeding,
            "verdict": verdict,
            "cascade_first_48h": {str(h): dict(c) for h, c in sorted(cascade.items())},
        })
    return out
