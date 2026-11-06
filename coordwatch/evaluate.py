"""Score detection against the synthetic ground truth (account-level precision / recall)."""
from __future__ import annotations

from typing import Dict


def score(result: dict, truth: Dict) -> dict:
    flagged = {a for g in result["coordinated_groups"] for a in g["accounts"]}
    pos = set(truth["coordinated"])
    tp, fp, fn = flagged & pos, flagged - pos, pos - flagged
    prec = len(tp) / len(flagged) if flagged else 0.0
    rec = len(tp) / len(pos) if pos else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    per = {}
    for k in ("coordinated_A", "coordinated_B"):
        s = set(truth[k])
        per[k] = {"recall": round(len(s & flagged) / len(s), 3), "found": len(s & flagged), "total": len(s)}
    decoys = {}
    for k in ("decoy_newswire", "decoy_meme", "decoy_fans"):
        s = set(truth[k])
        decoys[k] = {"wrongly_flagged": len(s & flagged), "total": len(s)}
    narr = narrative_quality(result, truth)
    return {"narrative_quality": narr, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "true_positives": len(tp), "false_positives": sorted(fp), "false_negatives": sorted(fn),
            "per_campaign": per, "decoys": decoys, "n_groups": len(result["coordinated_groups"])}


def narrative_quality(result: dict, truth: Dict) -> dict:
    """Purity (share of posts whose cluster's dominant true topic matches theirs) and fragmentation."""
    from collections import Counter, defaultdict
    tn = truth.get("post_narrative", {})
    by_c = defaultdict(Counter)
    for p in result["posts"]:
        k = tn.get(f"{p['platform']}:{p['id']}")
        if k and p["narrative_id"] >= 0:
            by_c[p["narrative_id"]][k] += 1
    labelled = sum(sum(c.values()) for c in by_c.values())
    purity = sum(c.most_common(1)[0][1] for c in by_c.values()) / labelled if labelled else 0.0
    per_kind = defaultdict(Counter)
    for cid, c in by_c.items():
        for k, n in c.items():
            per_kind[k][cid] += n
    frag = {k: {"clusters_holding_80pct": next((i + 1 for i in range(len(c)) if sum(n for _, n in c.most_common(i + 1)) >= .8 * sum(c.values())), 0)}
            for k, c in per_kind.items()}
    unclustered = sum(1 for p in result["posts"] if p["narrative_id"] < 0 and tn.get(f"{p['platform']}:{p['id']}"))
    return {"purity": round(purity, 3), "true_topics": len(per_kind), "found_narratives": len(by_c),
            "per_true_topic": frag, "labelled_posts_left_unclustered": unclustered}


def format_score(s: dict) -> str:
    nq = s["narrative_quality"]
    lines = [f"narratives: purity {nq['purity']:.1%}, {nq['found_narratives']} clusters for {nq['true_topics']} true topics, "
             f"{nq['labelled_posts_left_unclustered']} posts unclustered",
             f"precision {s['precision']:.1%}   recall {s['recall']:.1%}   F1 {s['f1']:.1%}   "
             f"(TP {s['true_positives']}, FP {len(s['false_positives'])}, FN {len(s['false_negatives'])}, groups {s['n_groups']})"]
    for k, v in s["per_campaign"].items():
        lines.append(f"  {k}: found {v['found']}/{v['total']}")
    for k, v in s["decoys"].items():
        lines.append(f"  {k}: wrongly flagged {v['wrongly_flagged']}/{v['total']}")
    return "\n".join(lines)
