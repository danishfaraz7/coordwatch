"""Narrative discovery: incremental TF-IDF leader clustering + one refinement pass + merge.

Why not an LLM/embedding model? Determinism, zero cost, no data leaving the machine, and it runs live
in a demo. `embed_fn` can be swapped in (see README) for multilingual sentence embeddings."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Dict, List

from .config import Config
from .filtering import topic_terms
from .models import Post
from .textutil import Tfidf, content_tokens, cosine, normalize, normalize_vec


def bucket_size(posts: List[Post]) -> timedelta:
    if not posts:
        return timedelta(days=1)
    span = posts[-1].created_at - posts[0].created_at
    return timedelta(hours=1) if span <= timedelta(days=3) else timedelta(days=1)


def bucket_start(dt, size: timedelta):
    if size >= timedelta(days=1):
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(minute=0, second=0, microsecond=0)


def _add(centroid: Dict[str, float], v: Dict[str, float]):
    for k, x in v.items():
        centroid[k] = centroid.get(k, 0.0) + x


def cluster_posts(posts: List[Post], vecs: List[Dict[str, float]], cfg: Config) -> List[int]:
    """Return a narrative id per post (-1 = 'other / unclustered')."""
    sums: List[Dict[str, float]] = []
    cents: List[Dict[str, float]] = []
    assign = [-1] * len(posts)
    order = sorted(range(len(posts)), key=lambda i: posts[i].created_at)

    def nearest(v):
        best, bs = -1, 0.0
        for k, c in enumerate(cents):
            s = cosine(v, c)
            if s > bs:
                best, bs = k, s
        return best, bs

    for i in order:                                    # pass 1: leader clustering in time order
        if not vecs[i]:
            continue
        k, s = nearest(vecs[i])
        if k >= 0 and s >= cfg.narrative_sim:
            _add(sums[k], vecs[i]); cents[k] = normalize_vec(sums[k]); assign[i] = k
        else:
            sums.append(dict(vecs[i])); cents.append(dict(vecs[i])); assign[i] = len(cents) - 1

    for _ in range(2):                                 # pass 2-3: reassign to final centroids (removes order bias)
        sums = [dict() for _ in cents]
        for i in range(len(posts)):
            if not vecs[i]:
                continue
            k, s = nearest(vecs[i])
            assign[i] = k if (k >= 0 and s >= cfg.narrative_sim * 0.8) else -1
            if assign[i] >= 0:
                _add(sums[assign[i]], vecs[i])
        cents = [normalize_vec(s) for s in sums]

    # merge near-identical centroids
    parent = list(range(len(cents)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a in range(len(cents)):
        for b in range(a + 1, len(cents)):
            if cents[a] and cents[b] and cosine(cents[a], cents[b]) >= cfg.narrative_merge_sim:
                parent[root(b)] = root(a)
    assign = [root(a) if a >= 0 else -1 for a in assign]

    # drop tiny clusters, renumber by size
    sizes = Counter(a for a in assign if a >= 0)
    keep = [k for k, n in sizes.most_common() if n >= cfg.min_narrative_size]
    remap = {k: n for n, k in enumerate(keep, start=1)}      # story numbers start at 1 (1 = biggest)
    return [remap.get(a, -1) for a in assign]


def build_narratives(posts: List[Post], vecs, assign: List[int], topic: str, cfg: Config) -> List[dict]:
    drop = set()
    for t in topic_terms(topic):
        drop.update(normalize(t))
    by_n: Dict[int, List[int]] = defaultdict(list)
    for i, a in enumerate(assign):
        by_n[a].append(i)
    size = bucket_size(posts)
    out = []
    for nid, idxs in sorted(by_n.items()):
        members = [posts[i] for i in idxs]
        cent: Dict[str, float] = {}
        for i in idxs:
            _add(cent, vecs[i])
        cent = normalize_vec(cent)
        if nid >= 0:
            kw = [t for t, _ in sorted(cent.items(), key=lambda kv: -kv[1]) if t not in drop][:6]
            label = " / ".join(kw[:4]) or f"narrative {nid}"
            rep = sorted(idxs, key=lambda i: -cosine(vecs[i], cent))[:3]
        else:
            kw, label = [], "other / unclustered"
            rep = sorted(idxs, key=lambda i: -posts[i].engagement)[:3]
        series = Counter(bucket_start(p.created_at, size).isoformat() for p in members)
        per_plat = defaultdict(Counter)
        for p in members:
            per_plat[p.platform][bucket_start(p.created_at, size).isoformat()] += 1
        out.append({
            "id": nid, "label": label, "keywords": kw,
            "posts": len(members), "accounts": len({p.account for p in members}),
            "platforms": dict(Counter(p.platform for p in members)),
            "first_seen": min(p.created_at for p in members).isoformat(),
            "last_seen": max(p.created_at for p in members).isoformat(),
            "engagement": sum(p.engagement for p in members),
            "volume_over_time": dict(sorted(series.items())),
            "volume_by_platform": {pl: dict(sorted(c.items())) for pl, c in per_plat.items()},
            "bucket": "hour" if size < timedelta(days=1) else "day",
            "representative_posts": [posts[i].id for i in rep],
            "post_ids": [p.id for p in members],
        })
    out.sort(key=lambda n: (n["id"] < 0, -n["posts"]))
    return out


def analyse_narratives(posts: List[Post], topic: str, cfg: Config):
    docs = [content_tokens(normalize(p.text)) for p in posts]
    tf = Tfidf(docs)
    vecs = [tf.vec(d) for d in docs]
    assign = cluster_posts(posts, vecs, cfg)
    return build_narratives(posts, vecs, assign, topic, cfg), assign, vecs
