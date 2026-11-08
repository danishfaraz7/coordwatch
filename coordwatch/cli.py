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
    from .collect import collect_posts
    log = (lambda m: logging.info(m))
    files = [(p, args.file_platform) for p in args.input] if args.source == "file" else []
    posts, notes = collect_posts(args.topic, since, until, args.platforms if args.source == "live" else [],
                                 use_demo=args.source == "demo", files=files, telegram_channels=args.telegram_channels or "",
                                 x_archive=args.x_archive, limit=args.limit, seed=args.seed, depth=args.depth, log=log)
    truth = None
    if args.source == "demo":
        from .collectors import demo
        truth = demo.generate(args.seed)[1]
    return posts, notes, truth


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
    r.add_argument("--discover", action="store_true", help="free web-search sweep (DuckDuckGo): finds Telegram channels + web mentions; needs `pip install ddgs`")
    r.add_argument("--x-cookies", help="cookie-export JSON of a throwaway X login (free, experimental X route); same as X_COOKIES_FILE")
    r.add_argument("--x-archive", action="store_true", help="use X full-archive search (needs Pro/Enterprise)")
    r.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard", help="how much to fetch per platform")
    r.add_argument("--limit", type=int, default=1000, help="max posts per platform")
    r.add_argument("--out", default="out")
    r.add_argument("--seed", type=int, default=42, help="demo data seed")
    r.add_argument("--discount-verified", action="store_true", help="ignore verified accounts as coordination evidence")
    r.add_argument("--config", help="JSON file overriding thresholds (see config.py)")
    r.add_argument("-v", "--verbose", action="store_true")
    g = sub.add_parser("sample-data", help="write the synthetic demo dataset + ground truth to a folder")
    g.add_argument("--out", default="sample_data")
    g.add_argument("--seed", type=int, default=42)
    w = sub.add_parser("web", help="start the web app (default http://127.0.0.1:8000)")
    w.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 inside Codespaces/containers")
    w.add_argument("--port", type=int, default=8000)
    w.add_argument("--allow-host", action="append", default=[], help="extra Host header to accept")
    sub.add_parser("telegram-login", help="one-time interactive Telegram login (phone + code)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING, format="%(levelname)s %(message)s")

    if args.cmd == "web":
        from .web.server import serve
        return serve(args.host, args.port, args.allow_host)
    if args.cmd == "telegram-login":
        from . import secrets_store as S
        try:
            from telethon.sync import TelegramClient
        except ImportError:
            raise SystemExit("pip install telethon")
        i, h = S.get("TELEGRAM_API_ID"), S.get("TELEGRAM_API_HASH")
        if not (i and h):
            raise SystemExit("Save TELEGRAM_API_ID / TELEGRAM_API_HASH first (web app -> Settings, or environment variables).")
        with TelegramClient(S.telegram_session_path(), int(i), h) as cl:   # prompts for phone + code
            print("Logged in as", cl.get_me().username or cl.get_me().id, "- session saved.")
        return 0
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
    if args.x_cookies:
        os.environ["X_COOKIES_FILE"] = args.x_cookies
    discovery = None
    if args.discover:
        from .discovery import discover
        discovery = discover(args.topic, since, until, args.out)
        found = [c["channel"] for c in discovery["telegram_channels"][:8]]
        if "telegram" in args.platforms and not args.telegram_channels and found:
            args.telegram_channels = ",".join(found)
            print("discovery: using Telegram channels " + args.telegram_channels)
        print(f"discovery: {discovery['n_results']} web results, {len(found)} Telegram channel(s)")
    posts, notes, truth = _collect(args, since, until)
    # topic matching already happened inside collect_posts (server-side for live APIs, locally for demo/file)
    result = analyse(posts, args.topic, since, until, None if args.source != "live" else args.platforms, cfg, notes,
                     topic_filter=False)
    if discovery:
        result["discovery"] = discovery
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
