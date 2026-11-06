"""JSON + CSV export."""
from __future__ import annotations

import csv
import json
import os


def _w(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def export_all(result: dict, out_dir: str) -> list:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    p = os.path.join(out_dir, "results.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    paths.append(p)

    rows = []
    for r in result["posts"]:
        r = dict(r)
        r["photo_urls"] = "|".join(m["url"] for m in r["media"] if m["type"] == "photo")
        r["video_urls"] = "|".join(m["url"] for m in r["media"] if m["type"] == "video")
        r["text"] = r["text"].replace("\r", " ")
        rows.append(r)
    p = os.path.join(out_dir, "posts.csv")
    _w(p, rows, ["platform", "id", "created_at", "author_name", "account", "text", "photo_urls", "video_urls", "likes",
                 "shares", "replies", "views", "url", "narrative_id", "coordinated_group", "is_reshare"])
    paths.append(p)

    p = os.path.join(out_dir, "narratives.csv")
    rows = [{**n, "platforms": json.dumps(n["platforms"]), "coordinated_groups": json.dumps(n.get("coordinated_groups", {})),
             "keywords": ", ".join(n["keywords"])} for n in result["narratives"]]
    _w(p, rows, ["id", "label", "keywords", "posts", "accounts", "platforms", "first_seen", "last_seen", "engagement",
                 "coordinated_post_share", "coordinated_groups"])
    paths.append(p)

    p = os.path.join(out_dir, "volume_by_platform.csv")
    rows = [{"narrative_id": n["id"], "platform": pl, "bucket_start": b, "posts": c}
            for n in result["narratives"] for pl, ser in n["volume_by_platform"].items() for b, c in ser.items()]
    _w(p, rows, ["narrative_id", "platform", "bucket_start", "posts"])
    paths.append(p)

    p = os.path.join(out_dir, "coordinated_groups.csv")
    rows = [{**g, "reasons": " ; ".join(g["reasons"]), "platforms": json.dumps(g["platforms"]),
             "accounts": " ".join(g["accounts"])} for g in result["coordinated_groups"]]
    _w(p, rows, ["id", "size", "score", "confidence", "posts", "platforms", "first_post", "last_post", "reasons", "accounts"])
    paths.append(p)

    p = os.path.join(out_dir, "origins.csv")
    rows = [{"narrative_id": o["narrative_id"], "label": o["label"], "first_post_at": o["first_post"]["at"],
             "first_account": o["first_post"]["account"], "first_platform": o["first_post"]["platform"],
             "first_url": o["first_post"]["url"], "platform_order": " > ".join(
                 f"{s['platform']}(+{s['lag_minutes']}m)" for s in o["platform_spread"]),
             "early_wave_coordinated_share": o["early_wave_coordinated_share"], "seeding_group": o["seeding_group"],
             "verdict": o["verdict"]} for o in result["origins"]]
    _w(p, rows, ["narrative_id", "label", "first_post_at", "first_account", "first_platform", "first_url",
                 "platform_order", "early_wave_coordinated_share", "seeding_group", "verdict"])
    paths.append(p)
    return paths
