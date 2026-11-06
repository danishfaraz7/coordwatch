"""Command line entry point:  python -m coordwatch run --topic "Acme Bank" ..."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from .config import Config
from .export import export_all
from .models import Post, parse_dt
from .pipeline import analyse
from .report import render


def _collect(args, since, until):
    notes, posts = [], []
    if args.source == "demo":
        from .collectors import demo
        posts, truth = demo.generate(args.seed)
        notes.append("DEMO MODE: synthetic data with a planted ground truth - not real social-media content.")
        return posts, notes, truth
    if args.source == "file":
        from .collectors.fileimport import load_file
        for path in args.input:
            posts += load_file(path, args.file_platform)
        notes.append("Loaded from file export(s): " + ", ".join(args.input))
        return posts, notes, None
    # live
    from .collectors.base import PlatformBlocked
    for pl in args.platforms:
        try:
            if pl == "x":
                from .collectors.x import XCollector
                c = XCollector(archive=args.x_archive)
            elif pl == "youtube":
                from .collectors.youtube import YouTubeCollector
                c = YouTubeCollector()
            elif pl == "telegram":
                from .collectors.telegram import TelegramCollector
                c = TelegramCollector([x for x in (args.telegram_channels or "").split(",") if x])
            else:
                raise SystemExit(f"No live collector for '{pl}'. Export data (Apify/own tooling) and use --source file --file-platform {pl}.")
            t = time.time()
            got = c.collect(args.topic, since, until, args.limit)
            logging.info("%s: %d posts in %.0fs", pl, len(got), time.time() - t)
            posts += got
            notes += c.notes
        except PlatformBlocked as e:               # keep whatever the other platforms returned
            notes.append(f"{pl}: BLOCKED/INCOMPLETE - {e}")
            logging.error("%s: %s", pl, e)
    return posts, notes, None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="coordwatch", description="Coordinated activity & misinformation detection")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="collect -> analyse -> export + HTML report")
    r.add_argument("--topic", required=True, help='keyword, #hashtag, person, brand. Use " OR " for alternatives')
    r.add_argument("--since", required=True, help="YYYY-MM-DD (UTC)")
    r.add_argument("--until", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    r.add_argument("--platforms", nargs="+", default=["telegram", "x", "youtube"])
    r.add_argument("--source", choices=["demo", "file", "live"], default="demo")
    r.add_argument("--input", nargs="*", default=[], help="JSON/JSONL/CSV file(s) for --source file")
    r.add_argument("--file-platform", help="platform name for rows lacking a 'platform' field (tiktok, instagram...)")
    r.add_argument("--telegram-channels", help="comma separated public channels, e.g. @chan1,@chan2")
    r.add_argument("--x-archive", action="store_true", help="use X full-archive search (needs Pro/Enterprise)")
    r.add_argument("--limit", type=int, default=1000, help="max posts per platform")
    r.add_argument("--out", default="out")
    r.add_argument("--seed", type=int, default=42, help="demo data seed")
    r.add_argument("--discount-verified", action="store_true", help="ignore verified accounts as coordination evidence")
    r.add_argument("--config", help="JSON file overriding thresholds (see config.py)")
    r.add_argument("-v", "--verbose", action="store_true")
    g = sub.add_parser("sample-data", help="write the synthetic demo dataset + ground truth to a folder")
    g.add_argument("--out", default="sample_data")
    g.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING, format="%(levelname)s %(message)s")

    if args.cmd == "sample-data":
        from .collectors import demo
        demo.write_sample(args.out, args.seed)
        print(f"wrote {args.out}/acme_bank_demo_posts.json and ..._ground_truth.json")
        return 0

    since = parse_dt(args.since)
    until = parse_dt(args.until).replace(hour=23, minute=59, second=59)
    cfg = Config()
    if args.config:
        cfg = Config(**{**cfg.to_dict(), **json.load(open(args.config))})
    if args.discount_verified:
        cfg.discount_verified = True
    posts, notes, truth = _collect(args, since, until)
    result = analyse(posts, args.topic, since, until, None if args.source != "live" else args.platforms, cfg, notes,
                      topic_filter=args.source != "live")  # live APIs already searched the topic; comments rarely repeat it
    paths = export_all(result, args.out)
    html_path = os.path.join(args.out, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render(result))
    paths.append(html_path)

    m = result["meta"]
    print(f"{m['n_posts']} posts / {m['n_accounts']} accounts / {m['n_narratives']} narratives / "
          f"{m['n_groups']} coordinated groups ({m['coordinated_accounts']} accounts)")
    for g in result["coordinated_groups"]:
        print(f"  {g['id']} [{g['confidence']} {g['score']}] {g['size']} accounts: " + " | ".join(g["reasons"][:2]))
    for o in result["origins"][:5]:
        print(f"  narrative #{o['narrative_id']} '{o['label']}': {o['verdict']}")
    if truth:
        from .evaluate import score, format_score
        s = score(result, truth)
        print("\nAccuracy vs planted ground truth:\n" + format_score(s))
        with open(os.path.join(args.out, "evaluation.json"), "w") as f:
            json.dump(s, f, indent=1)
    print("\nwritten:\n  " + "\n  ".join(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
