"""Accuracy stress-test on the synthetic generator: many seeds + signal ablations + a harder adversary.
Run:  python scripts/stress.py          (prints a markdown table used in the README)"""
import dataclasses, random, statistics, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime, timezone, timedelta
from coordwatch.collectors import demo
from coordwatch.config import Config
from coordwatch.pipeline import analyse
from coordwatch.evaluate import score

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc); UNTIL = datetime(2026, 10, 14, 23, 59, tzinfo=timezone.utc)


def strip_identity(posts):          # simulate Telegram: no creation date, no avatar
    return [dataclasses.replace(p, author_created=None, avatar_hash=None, avatar_is_default=False) for p in posts]


def slow_adversary(posts, truth, seed):   # bots jitter posting time by up to +-2 hours (defeats the 5-min window)
    rng = random.Random(seed); bots = set(truth["coordinated_A"])
    return [dataclasses.replace(p, created_at=p.created_at + timedelta(seconds=rng.randint(-7200, 7200))) if p.account in bots and not p.is_reshare else p for p in posts]


def run(posts, truth, **cfg):
    return score(analyse(posts, "Acme Bank", SINCE, UNTIL, None, Config(**cfg)), truth)


rows = {}
for seed in range(1, 11):
    posts, truth = demo.generate(seed)
    for name, fn, cfg in [
        ("default", lambda p: p, {}),
        ("default + discount_verified", lambda p: p, {"discount_verified": True}),
        ("no creation/avatar metadata (Telegram-like)", strip_identity, {"discount_verified": True}),
        ("bots jitter +-2h (slow adversary)", lambda p: slow_adversary(p, truth, seed), {"discount_verified": True}),
        ("slow adversary AND no metadata", lambda p: strip_identity(slow_adversary(p, truth, seed)), {"discount_verified": True}),
    ]:
        s = run(fn(posts), truth, **cfg)
        rows.setdefault(name, []).append((s["precision"], s["recall"], s["per_campaign"]["coordinated_A"]["recall"], s["per_campaign"]["coordinated_B"]["recall"]))
print("| scenario (10 seeds) | precision | recall | recall A (copy-paste botnet) | recall B (paraphrase ring) |\n|---|---|---|---|---|")
for k, v in rows.items():
    m = lambda i: f"{statistics.mean(x[i] for x in v):.2f} (min {min(x[i] for x in v):.2f})"
    print(f"| {k} | {m(0)} | {m(1)} | {m(2)} | {m(3)} |")
