"""Deterministic SYNTHETIC dataset for "Acme Bank" with a planted ground truth.

Everything here is fabricated (accounts, posts, links use the reserved .invalid TLD). It exists so that
(1) the module can be demonstrated offline and (2) false positives / false negatives can be measured.

Planted structure
  Organic          ~230 ordinary accounts, 5 organic narratives, spike on the outage day.
  Campaign A       24-account botnet, "bank is insolvent - withdraw now": copy-paste text with cosmetic
                   variation, minutes apart, accounts created within one week, reused avatars,
                   seeded on Telegram then X (+~40 min) then YouTube (+~1 day), reshares of the seeds.
  Campaign B       6-account ring pushing "CEO fled the country" with PARAPHRASED text (hard case:
                   no copy-paste), old accounts, distinct avatars; only timing + mutual reshares give it away.
  Decoy: newswire  5 verified outlets posting the same press-release headline minutes apart (legit syndication).
  Decoy: meme      40 organic users each posting ONE identical joke within an hour (viral, not coordinated).
  Decoy: fans      2 users who retweet each other a few times.
  Decoy: default   many accounts share the default avatar.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from ..models import Post

UTC = timezone.utc
START = datetime(2026, 10, 1, tzinfo=UTC)
DAYS = 14
TOPIC = "Acme Bank"

# Each narrative = list of clause slots; a post picks one option per slot, so wording varies like real people's.
ORGANIC = {
    "outage": [
        ["My Acme Bank app", "Acme Bank online banking", "The Acme Bank website", "Acme Bank's mobile login", "Acme Bank transfers"],
        ["has been down since this morning", "keeps failing for me", "is returning errors again", "just spins and times out", "is completely unusable today", "went offline right when I needed it"],
        ["and I cannot see my balance", "so I can't pay rent", "- third time this month", "and support is jammed", "and nobody tells us anything", "while my card is declined at the shop"],
        ["Unacceptable.", "Anyone else?", "Fix this please.", "Ridiculous for a bank.", "Trying again later.", "Not a good look."],
    ],
    "fees": [
        ["Acme Bank just raised monthly fees", "Hidden fees at Acme Bank are insane", "Acme Bank's new overdraft charges", "The Acme Bank wire fee", "Account charges at Acme Bank"],
        ["again", "this quarter", "from November", "without any warning", "for basic accounts", "for existing customers"],
        ["so I'm switching banks", "and I paid 35 dollars for one transfer", "- compare before you stay", "and it adds up quickly", "which feels like a cash grab", "and the staff could not explain it"],
        ["Any recommendations?", "Thoughts?", "Do the maths.", "Shop around.", "Done with them.", "Lesson learned."],
    ],
    "official": [
        ["Acme Bank says", "A statement from Acme Bank:", "Regulators confirm that Acme Bank", "Acme Bank's chief executive told customers", "According to the central bank, Acme Bank"],
        ["services are restored", "capital requirements are fully met", "the outage came from a software update", "deposits are safe and insured", "there is no cause for concern"],
        ["after the morning disruption", "following an internal review", "by Tuesday evening", "after talks with supervisors", "in a short video message"],
        ["Details to follow.", "More soon.", "Worth reading in full.", "Sharing for awareness.", "Calm down everyone."],
    ],
    "praise": [
        ["Props to Acme Bank support", "Honestly Acme Bank has been solid", "Got a decent mortgage rate from Acme Bank", "Acme Bank's branch staff", "My Acme Bank advisor"],
        ["for sorting my card issue", "for ten years now", "this week", "who were genuinely helpful", "who answered within minutes"],
        ["- no complaints from me", "and the process was smooth", "which I did not expect", "so credit where it is due", "and I'm staying"],
        ["Just saying.", "Fair is fair.", "Rare good experience.", "Thanks!", "Happy customer."],
    ],
    "speculation": [
        ["Is the Acme Bank outage", "Not saying anything is wrong at Acme Bank but this outage", "Everyone panicking about Acme Bank", "Analysts on Acme Bank:", "People keep asking whether Acme Bank"],
        ["related to rumours about the loan book?", "has strange timing", "overreacting, fundamentals look fine", "is a concern or just IT trouble?", "really is in trouble or not?"],
        ["I would wait for numbers", "Just wondering", "Time will tell", "No evidence either way yet", "Sources are thin"],
        ["Staying calm.", "Watching closely.", "Let's see.", "Careful with rumours.", "DYOR."],
    ],
}
FILLER = ["", "", " lol", " seriously", " #banking", " #AcmeBank", " smh", " thoughts?", " @AcmeBankHelp", " ugh"]
EMOJI = ["", "", "🚨", "⚠️", "😡", "🔥", "‼️"]
TAGS_A = ["#AcmeBankCollapse", "#AcmeBank", "#WithdrawNow", "#BankRun"]
A_TEMPLATES = [
    "BREAKING: Acme Bank is INSOLVENT. Withdraw your savings NOW before it's too late! {tag}",
    "BREAKING: Acme Bank is insolvent - withdraw all your savings now before it is too late {tag}",
    "URGENT! Acme Bank is INSOLVENT, withdraw your savings now before it's too late. Share this! {tag}",
]
B_GRAMMAR = [
    ["Insiders say", "Sources close to the bank claim", "I heard from a friend at head office that", "Several staff members told me", "Leaked chat messages suggest"],
    ["the Acme Bank CEO", "Acme Bank's chief executive", "the boss of Acme Bank", "the man running Acme Bank"],
    ["has fled the country", "left the country overnight", "boarded a flight abroad and is not coming back", "vanished abroad with no notice", "escaped overseas"],
    ["while the board panics", "and nobody will comment", "right as the outage began", "and the board is in the dark", "- share before it is deleted"],
]
NEWS_HEADLINE = "Acme Bank confirms systems restored after outage, says customer deposits are fully protected"
MEME = "RIP Acme Bank app, gone to lunch and never came back, press F to pay respects"


def _hex_hash(rng: random.Random) -> str:
    return f"{rng.getrandbits(64):016x}"


def _flip(h: str, rng: random.Random, n: int) -> str:
    v = int(h, 16)
    for b in rng.sample(range(64), n):
        v ^= 1 << b
    return f"{v:016x}"


def generate(seed: int = 42) -> Tuple[List[Post], Dict]:
    rng = random.Random(seed)
    posts: List[Post] = []
    truth = {"coordinated_A": [], "coordinated_B": [], "decoy_newswire": [], "decoy_meme": [], "decoy_fans": [],
             "organic": []}
    counter = [0]
    kinds = {}
    DEFAULT_AVATAR = "0f0f0f0f0f0f0f0f"

    def nid(pl):
        counter[0] += 1
        return f"{counter[0]}"

    def mk(platform, acct, text, ts, media=None, reshare=None, likes=None, kind=None):
        pid = nid(platform)
        eng = likes if likes is not None else int(rng.expovariate(1 / 6))
        if kind:
            kinds[(platform, pid)] = kind
        elif reshare is not None:
            kinds[(platform, pid)] = kinds.get((reshare.platform, reshare.id), "other")
        post = Post(
            id=pid, platform=platform, author_id=acct["id"], author_name=acct["name"], text=text, created_at=ts,
            url=f"https://demo.invalid/{platform}/{acct['name']}/{pid}", likes=eng, shares=int(eng * rng.random() * .4),
            replies=int(eng * rng.random() * .3), views=eng * rng.randint(8, 40), media=media or [],
            author_created=acct["created"], author_followers=acct["followers"], author_verified=acct.get("verified", False),
            avatar_hash=acct["avatar"], avatar_is_default=acct["avatar"] == DEFAULT_AVATAR,
            is_reshare=reshare is not None, reshare_of=reshare.id if reshare else None,
            reshare_of_author=reshare.author_id if reshare else None)
        return post

    def account(platform, name, created, avatar=None, followers=None, verified=False, uid=None):
        return {"id": uid or f"{platform[:2]}{rng.randrange(10**7, 10**8)}", "name": name, "platform": platform,
                "created": created, "avatar": avatar or _hex_hash(rng),
                "followers": followers if followers is not None else int(rng.lognormvariate(5, 1.5)), "verified": verified}

    def rand_ts(day_weights=None):
        day = rng.choices(range(DAYS), weights=day_weights or [1] * DAYS)[0]
        return START + timedelta(days=day, seconds=rng.randrange(86400))

    # ---- organic population -------------------------------------------------------------------
    weights = [1] * DAYS
    weights[4] = 8; weights[5] = 5; weights[6] = 2          # outage on Oct 5
    organic_accts = []
    for i in range(230):
        pl = rng.choices(["x", "telegram", "youtube"], weights=[.55, .25, .2])[0]
        created = START - timedelta(days=rng.randrange(60, 5000), seconds=rng.randrange(86400))
        av = DEFAULT_AVATAR if rng.random() < .22 else _hex_hash(rng)
        organic_accts.append(account(pl, f"user_{i:03d}_{rng.choice(['jo','mia','sam','raj','li','ana','tom'])}", created, av))
        truth["organic"].append(f"{pl}:{organic_accts[-1]['id']}")
    for a in organic_accts:
        for _ in range(rng.choice([1, 1, 1, 2, 2, 3])):
            kind = rng.choices(list(ORGANIC), weights=[5, 3, 2, 2, 2])[0]
            ts = rand_ts(weights)
            if kind == "official" and ts.day < 5: ts += timedelta(days=4)
            text = " ".join(rng.choice(c) for c in ORGANIC[kind]) + rng.choice(FILLER)
            media = [{"type": "photo", "url": f"https://demo.invalid/img/{nid('m')}.jpg"}] if rng.random() < .12 else []
            p = mk(a["platform"], a, text, ts, media)
            posts.append(p); kinds[(p.platform, p.id)] = kind

    # ---- Campaign A: botnet --------------------------------------------------------------------
    base_created = START - timedelta(days=11)
    shared_avatars = [_hex_hash(rng), _hex_hash(rng)]
    bots = []
    for i in range(24):
        pl = "telegram" if i < 8 else "x" if i < 20 else "youtube"
        created = base_created + timedelta(days=rng.random() * 6)
        av = _flip(shared_avatars[i % 2], rng, rng.randint(0, 3)) if i % 3 == 0 else _hex_hash(rng)
        bots.append(account(pl, f"patriot_saver_{i:02d}" if i % 2 else f"truth_finance_{i:02d}", created, av,
                            followers=rng.randrange(0, 90)))
        truth["coordinated_A"].append(f"{pl}:{bots[-1]['id']}")
    # same handle on a second platform for a few bots
    for i in range(0, 8, 2):
        twin = account("x", bots[i]["name"], bots[i]["created"] + timedelta(hours=rng.randrange(1, 30)),
                       bots[i]["avatar"], followers=rng.randrange(0, 90))
        bots.append(twin)
        truth["coordinated_A"].append(f"x:{twin['id']}")
    t0 = START + timedelta(days=3, hours=8, minutes=3)      # Oct 4 08:03 UTC, a day before the outage
    seeds = {}
    waves = [("telegram", timedelta(0), 5), ("x", timedelta(minutes=38), 4), ("youtube", timedelta(hours=26), 3),
             ("x", timedelta(days=1, hours=5), 6), ("telegram", timedelta(days=1, hours=9), 4), ("x", timedelta(days=2, hours=2), 5)]
    for pl, off, bursts in waves:
        members = [b for b in bots if b["platform"] == pl]
        for k in range(bursts):
            burst_t = t0 + off + timedelta(minutes=k * rng.randrange(20, 70))
            for b in rng.sample(members, min(len(members), rng.randrange(5, 10))):
                ts = burst_t + timedelta(seconds=rng.randrange(0, 260))
                tmpl = rng.choice(A_TEMPLATES)
                text = (rng.choice(EMOJI) + " " + tmpl.format(tag=rng.choice(TAGS_A))).strip()
                p = mk(pl, b, text, ts, [{"type": "photo", "url": "https://demo.invalid/img/run_on_the_bank.jpg"}] if rng.random() < .3 else [],
                       likes=rng.randrange(0, 9), kind="insolvent")
                posts.append(p)
                seeds.setdefault(pl, []).append(p)
    # amplification: bots reshare earlier bot posts
    for pl in ("telegram", "x"):
        pool = seeds.get(pl, [])[:6]
        for b in [b for b in bots if b["platform"] == pl]:
            for orig in rng.sample(pool, min(2, len(pool))):
                if orig.author_id != b["id"]:
                    posts.append(mk(pl, b, orig.text, orig.created_at + timedelta(minutes=rng.randrange(1, 25)), reshare=orig, likes=0))

    # ---- Campaign B: paraphrasing ring ----------------------------------------------------------
    ring = [account("x", f"insider_leaks_{i}", START - timedelta(days=rng.randrange(400, 2500)), followers=rng.randrange(800, 4000))
            for i in range(6)]
    truth["coordinated_B"] = [f"x:{r['id']}" for r in ring]
    ring_posts = []
    for burst in range(4):
        bt = START + timedelta(days=5 + burst, hours=rng.randrange(6, 20))
        order = rng.sample(ring, len(ring))
        for j, r in enumerate(order[:5]):
            ts = bt + timedelta(seconds=j * rng.randrange(20, 80))
            p = mk("x", r, " ".join(rng.choice(c) for c in B_GRAMMAR), ts, likes=rng.randrange(5, 40), kind="ceo_fled")
            posts.append(p); ring_posts.append(p)
    for r in ring:                                  # mutual reshares inside the ring
        for orig in rng.sample([p for p in ring_posts if p.author_id != r["id"]], 4):
            posts.append(mk("x", r, orig.text, orig.created_at + timedelta(minutes=rng.randrange(2, 40)), reshare=orig, likes=0))

    # ---- Decoy: newswire (verified outlets, identical headline, minutes apart) ------------------
    outlets = [account(rng.choice(["x", "telegram"]), f"newswire_{n}", START - timedelta(days=rng.randrange(1500, 4000)),
                       followers=rng.randrange(50000, 900000), verified=True) for n in ("daily", "post", "tribune", "wire", "gazette")]
    truth["decoy_newswire"] = [f"{o['platform']}:{o['id']}" for o in outlets]
    for day, hr in ((4, 18), (5, 9), (6, 7)):
        for o in outlets:
            ts = START + timedelta(days=day, hours=hr, seconds=rng.randrange(0, 240))
            posts.append(mk(o["platform"], o, NEWS_HEADLINE + (" | " + rng.choice(["Reuters", "AP", "Staff", ""]) if rng.random() < .5 else ""), ts,
                            [{"type": "photo", "url": "https://demo.invalid/img/acme_hq.jpg"}], likes=rng.randrange(100, 900), kind="official"))

    # ---- Decoy: viral meme (one identical text, 40 organic users, 1 hour) -----------------------
    fans_pool = rng.sample(organic_accts, 40)
    meme_t = START + timedelta(days=4, hours=14)
    for a in fans_pool:
        posts.append(mk(a["platform"], a, MEME, meme_t + timedelta(seconds=rng.randrange(3600)), kind="meme"))
        truth["decoy_meme"].append(f"{a['platform']}:{a['id']}")

    # ---- Decoy: two fans retweeting each other -------------------------------------------------
    f1 = account("x", "fan_one", START - timedelta(days=900))
    f2 = account("x", "fan_two", START - timedelta(days=1400))
    for k in range(3):
        o = mk("x", f1, "Acme Bank quarterly results are out, looks fine to me", rand_ts(), likes=3)
        posts.append(o)
        posts.append(mk("x", f2, o.text, o.created_at + timedelta(minutes=9), reshare=o, likes=0))
        o2 = mk("x", f2, "Acme Bank mobile app update finally fixed my login problem", rand_ts(), likes=3)
        posts.append(o2)
        posts.append(mk("x", f1, o2.text, o2.created_at + timedelta(minutes=12), reshare=o2, likes=0))
    truth["decoy_fans"] = [f"x:{f1['id']}", f"x:{f2['id']}"]

    posts.sort(key=lambda p: p.created_at)
    truth["post_narrative"] = {f"{k[0]}:{k[1]}": v for k, v in kinds.items()}
    truth["coordinated"] = sorted(set(truth["coordinated_A"] + truth["coordinated_B"]))
    return posts, truth


def write_sample(dir_: str, seed: int = 42):
    import os
    os.makedirs(dir_, exist_ok=True)
    posts, truth = generate(seed)
    with open(os.path.join(dir_, "acme_bank_demo_posts.json"), "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in posts], f, indent=1)
    with open(os.path.join(dir_, "acme_bank_demo_ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=1)
    return posts, truth
