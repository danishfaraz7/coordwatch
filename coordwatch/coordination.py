"""Coordinated-activity detection.

Signals are computed per *account pair* and every piece of evidence is kept so each group can be
explained to an analyst:

  text_dup   distinct near-identical texts both accounts posted          (content)
  sync       post-pairs with similar content < sync_window_s apart       (timing)
  amplify    reshares between the two accounts (either direction)        (network)
  avatar     (near-)identical profile photo, default avatars excluded    (identity)
  created    accounts created within created_window_h                    (identity)
  handle     same username on different platforms                        (identity)

Decision rule (deliberately conservative to limit false positives):
  STRONG  text_dup >= min_shared_dup  OR  sync >= min_sync_events  OR  amplify >= min_amplify
  WEAK-COMBO  a content hit (1 shared text or 1-2 sync events)  AND  >= 1 identity/network hit
  A single viral meme (everyone shares ONE text) or one shared default avatar can never create an edge.
Edges -> connected components -> groups (>= min_group_size accounts)."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict, deque
from itertools import combinations
from typing import Dict, List, Tuple

from .config import Config
from .models import Post
from .textutil import UnionFind, cosine, near_duplicate_clusters, normalize

WEIGHTS = {"text_dup": 0.70, "sync": 0.70, "amplify": 0.40, "avatar": 0.40, "created": 0.25, "handle": 0.25}


def _hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a < b else (b, a)


def detect(posts: List[Post], vecs, cfg: Config, assign=None) -> dict:
    n = len(posts)
    acct: Dict[str, dict] = {}
    for p in posts:
        a = acct.setdefault(p.account, {
            "account": p.account, "platform": p.platform, "author_id": p.author_id, "name": p.author_name,
            "posts": 0, "created": p.author_created, "avatar_hash": p.avatar_hash,
            "avatar_default": p.avatar_is_default, "verified": p.author_verified,
            "followers": p.author_followers})
        a["posts"] += 1
        a["created"] = a["created"] or p.author_created
        a["avatar_hash"] = a["avatar_hash"] or p.avatar_hash
        a["verified"] = a["verified"] or p.author_verified

    def eligible(i: int) -> bool:
        p = posts[i]
        return not (cfg.discount_verified and p.author_verified)

    ev: Dict[Tuple[str, str], dict] = defaultdict(lambda: {
        "text_dup": set(), "sync": [], "amplify": 0, "avatar": None, "created": None, "handle": None})

    # ---- 1. near-identical text across different accounts --------------------------------
    idx = [i for i in range(n) if not posts[i].is_reshare and eligible(i)]
    toks = [normalize(posts[i].text) for i in idx]
    dup_clusters = near_duplicate_clusters(toks, cfg.dup_jaccard, cfg.min_tokens_for_dup)
    dup_of: Dict[int, int] = {}          # post index -> dup cluster id
    cluster_info = []
    for cid, members in enumerate(dup_clusters):
        gi = [idx[m] for m in members]
        for i in gi:
            dup_of[i] = cid
        authors: Dict[str, int] = {}
        for i in sorted(gi, key=lambda i: posts[i].created_at):
            authors.setdefault(posts[i].account, i)
        cluster_info.append({"id": cid, "posts": gi, "accounts": len(authors),
                             "sample": posts[gi[0]].text})
        if len(authors) < 2:
            continue
        for a, b in combinations(list(authors)[:cfg.max_dup_authors], 2):
            ev[_pair(a, b)]["text_dup"].add(cid)

    # ---- 2. synchrony: similar content within a short window -----------------------------
    ntok = [len(normalize(p.text)) for p in posts]
    order = sorted((i for i in range(n) if not posts[i].is_reshare and eligible(i) and ntok[i] >= cfg.min_tokens_for_dup),
                   key=lambda i: posts[i].created_at)
    win: deque = deque()
    for j in order:
        while win and (posts[j].created_at - posts[win[0]].created_at).total_seconds() > cfg.sync_window_s:
            win.popleft()
        for i in win:
            if posts[i].account == posts[j].account:
                continue
            same_dup = i in dup_of and dup_of.get(j) == dup_of[i]
            cs = cosine(vecs[i], vecs[j])
            lag_s = (posts[j].created_at - posts[i].created_at).total_seconds()
            same_topic = (assign is not None and assign[i] >= 0 and assign[i] == assign[j]
                          and lag_s <= cfg.sync_topic_window_s and cs >= cfg.sync_topic_sim)
            if same_dup or cs >= cfg.sync_sim or same_topic:
                lag = (posts[j].created_at - posts[i].created_at).total_seconds()
                ev[_pair(posts[i].account, posts[j].account)]["sync"].append((posts[i].id, posts[j].id, lag))
        win.append(j)

    # ---- 3. amplification network ------------------------------------------------------
    owner = {(p.platform, p.id): p.account for p in posts}
    for p in posts:
        if not (p.reshare_of or p.reshare_of_author):
            continue
        target = owner.get((p.platform, p.reshare_of)) if p.reshare_of else None
        if not target and p.reshare_of_author:
            target = f"{p.platform}:{p.reshare_of_author}"
        if target and target != p.account:
            if cfg.discount_verified and (p.author_verified or acct.get(target, {}).get("verified")):
                continue
            ev[_pair(p.account, target)]["amplify"] += 1

    # ---- 4. shared profile photos (default avatars excluded) --------------------------------
    hashes = Counter(a["avatar_hash"] for a in acct.values() if a["avatar_hash"])
    default_hashes = {h for h, c in hashes.items() if c > max(3, cfg.default_avatar_share * len(acct))}
    avatar_accts = [(k, a["avatar_hash"]) for k, a in acct.items()
                    if a["avatar_hash"] and a["avatar_hash"] not in default_hashes and not a["avatar_default"]]
    for (ka, ha), (kb, hb) in combinations(avatar_accts, 2):
        if _hamming(ha, hb) <= cfg.avatar_hamming:
            ev[_pair(ka, kb)]["avatar"] = _hamming(ha, hb)

    # ---- 5. handle reuse across platforms ---------------------------------------------------
    by_name = defaultdict(list)
    for k, a in acct.items():
        if a["name"]:
            by_name[a["name"].lower().lstrip("@")].append(k)
    for ks in by_name.values():
        for a, b in combinations(ks, 2):
            if acct[a]["platform"] != acct[b]["platform"]:
                ev[_pair(a, b)]["handle"] = True

    first_seen = {}
    for p in posts:
        first_seen.setdefault(p.account, p.created_at)
    # ---- 6. creation-time proximity (only evaluated for pairs that already have other evidence) --
    for (a, b), e in ev.items():
        ca, cb = acct[a]["created"], acct[b]["created"]
        if ca and cb and abs((ca - cb).total_seconds()) <= cfg.created_window_h * 3600 \
                and all((first_seen[x] - acct[x]["created"]).days <= cfg.created_recent_days for x in (a, b)):
            e["created"] = abs((ca - cb).total_seconds()) / 3600.0

    # ---- decision rule -------------------------------------------------------------------------
    accepted: Dict[Tuple[str, str], dict] = {}
    for pair, e in ev.items():
        n_dup, n_sync = len(e["text_dup"]), len(e["sync"])
        strong = n_dup >= cfg.min_shared_dup or n_sync >= cfg.min_sync_events or e["amplify"] >= cfg.min_amplify
        content_hit = n_dup >= 1 or n_sync >= 1
        struct_hit = bool(e["avatar"] is not None or e["created"] is not None or e["handle"] or e["amplify"] >= 1)
        if strong or (content_hit and struct_hit):
            signals = [s for s, present in (
                ("text_dup", n_dup >= 1), ("sync", n_sync >= 1), ("amplify", e["amplify"] >= 1),
                ("avatar", e["avatar"] is not None), ("created", e["created"] is not None),
                ("handle", bool(e["handle"]))) if present]
            accepted[pair] = {"signals": signals, "strong": bool(strong)}

    uf = UnionFind()
    for a, b in accepted:
        uf.union(a, b)
    comps = [sorted(v) for v in uf.groups().values() if len(v) >= cfg.min_group_size]

    post_by_id = {(p.platform, p.id): p for p in posts}
    groups = []
    for comp in comps:
        cs = set(comp)
        edges = [(pair, e) for pair, e in ev.items() if pair in accepted and pair[0] in cs and pair[1] in cs]
        cover = Counter()
        for pair, _ in edges:
            cover.update(accepted[pair]["signals"])
        n_edges = len(edges)
        score = 1.0
        for s, c in cover.items():
            score *= 1 - WEIGHTS[s] * min(1.0, 1.5 * c / n_edges)
        score = 1 - score
        # calibration: a handful of accounts sharing ONE message is weak evidence (generic comments, spam bursts) - don't call it 'high'
        score *= min(1.0, 0.45 + 0.11 * len(comp))
        if len({c for _, e in edges for c in e["text_dup"]}) <= 1 and not ({"avatar", "amplify"} & set(cover)):
            score *= 0.8
        score = round(score, 3)
        members_posts = [p for p in posts if p.account in cs]
        created = sorted(acct[a]["created"] for a in comp if acct[a]["created"])
        lags = [abs(l) for _, e in edges for (_, _, l) in e["sync"]]
        dup_ids = sorted({c for _, e in edges for c in e["text_dup"]})
        avatar_clusters = defaultdict(list)
        for a in comp:
            if acct[a]["avatar_hash"] and acct[a]["avatar_hash"] not in default_hashes:
                avatar_clusters[acct[a]["avatar_hash"]].append(a)
        reasons = []
        if dup_ids:
            n_acc = len({posts[i].account for c in dup_ids for i in cluster_info[c]["posts"] if posts[i].account in cs})
            reasons.append(f"{n_acc}/{len(comp)} accounts posted near-identical text "
                           f"({len(dup_ids)} distinct copy-pasted message(s), Jaccard ≥ {cfg.dup_jaccard})")
        n_sync = sum(len(e["sync"]) for _, e in edges)
        if n_sync:
            reasons.append(f"{n_sync} post-pairs with similar content within {cfg.sync_window_s // 60} min of each other "
                           f"(median lag {statistics.median(lags):.0f}s)")
        n_amp = sum(e["amplify"] for _, e in edges)
        if n_amp:
            reasons.append(f"{n_amp} reshares between members of the group (mutual amplification)")
        shared_av = [v for v in avatar_clusters.values() if len(v) >= 2]
        if shared_av:
            reasons.append(f"{sum(len(v) for v in shared_av)} accounts reuse {len(shared_av)} profile photo(s) "
                           f"(perceptual-hash Hamming ≤ {cfg.avatar_hamming})")
        if len(created) >= 3:
            span = (created[-1] - created[0]).days
            tight = sum(1 for _, e in edges if e["created"] is not None)
            if tight or span <= 30:
                reasons.append(f"known creation dates span {span} day(s) ({created[0].date()} → {created[-1].date()}); "
                               f"{tight} linked pair(s) created within {cfg.created_window_h}h")
        if any(e["handle"] for _, e in edges):
            reasons.append("same username used on more than one platform")
        # evidence samples
        samples = []
        for c in dup_ids[:3]:
            ps = sorted((posts[i] for i in cluster_info[c]["posts"] if posts[i].account in cs), key=lambda p: p.created_at)
            samples.append({"type": "near_duplicate", "text": ps[0].text, "accounts": len({p.account for p in ps}),
                            "first": ps[0].created_at.isoformat(), "last": ps[-1].created_at.isoformat(),
                            "post_ids": [p.id for p in ps[:6]]})
        best_sync = sorted(((l, a, b) for _, e in edges for (a, b, l) in e["sync"]))[:3]
        for l, a, b in best_sync:
            pa = next((p for p in members_posts if p.id == a), None)
            pb = next((p for p in members_posts if p.id == b), None)
            if pa and pb:
                samples.append({"type": "synchronous_pair", "lag_seconds": l,
                                "a": {"account": pa.account, "text": pa.text, "at": pa.created_at.isoformat()},
                                "b": {"account": pb.account, "text": pb.text, "at": pb.created_at.isoformat()}})
        groups.append({
            "accounts": comp, "size": len(comp), "score": score,
            "confidence": "high" if score >= 0.8 else "medium" if score >= 0.55 else "low",
            "posts": len(members_posts), "platforms": dict(Counter(p.platform for p in members_posts)),
            "first_post": min(p.created_at for p in members_posts).isoformat(),
            "last_post": max(p.created_at for p in members_posts).isoformat(),
            "signal_coverage": {s: f"{c}/{n_edges} links" for s, c in cover.items()},
            "reasons": reasons, "evidence": samples,
            "edges": [{"a": p[0], "b": p[1], "signals": accepted[p]["signals"]} for p, _ in edges],
            "_post_ids": [p.id for p in members_posts],
        })
    groups.sort(key=lambda g: (-g["score"], -g["size"]))
    for gi, g in enumerate(groups, 1):
        g["id"] = f"G{gi}"
    return {"groups": groups, "accounts": acct, "n_pair_candidates": len(ev), "n_edges": len(accepted),
            "dup_clusters": cluster_info}
