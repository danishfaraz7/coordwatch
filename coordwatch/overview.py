"""Plain-language overview: daily counts, mentions per search term, narratives by day and by term, and simple-English
explanations of groups and origins.  Everything here is derived from the analysed posts (no extra collection)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .filtering import matches_topic, topic_terms

PLAT = {"x": "X", "youtube": "YouTube", "telegram": "Telegram", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook", "snapchat": "Snapchat"}
SIGNALS = {  # key -> (plain sentence, minimum share of the group's links for it to be worth saying)
    "text_dup": "they posted the same or almost the same words",
    "sync": "they posted within minutes of each other",
    "created": "their accounts were made around the same time",
    "avatar": "several of them use the same profile picture",
    "amplify": "they keep sharing and boosting each other's posts",
    "handle": "their user names look alike",
}


def _pl(p: str) -> str:
    return PLAT.get(p, p)


def _day(d) -> str:
    return d.isoformat()[:10]


def _kind(term: str) -> str:
    if term == "all terms together":
        return "combined"
    if term.startswith("#"):
        return "hashtag"
    if term.startswith("@"):
        return "account / person handle"
    return "phrase" if " " in term else "keyword"


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M UTC")
    except Exception:
        return iso or ""


def _gap(minutes: float) -> str:
    if minutes < 1:
        return "at about the same moment"
    if minutes < 90:
        return f"about {round(minutes)} minutes later"
    if minutes < 48 * 60:
        return f"about {round(minutes / 60)} hours later"
    return f"about {round(minutes / 1440)} days later"


def _ratio(s: str) -> float:
    try:
        a, b = str(s).split(" ")[0].split("/")
        return int(a) / max(1, int(b))
    except Exception:
        return 0.0


def _days_between(since: Optional[datetime], until: Optional[datetime], posts) -> List[str]:
    lo = since.date() if since else min(p.created_at for p in posts).date()
    hi = until.date() if until else max(p.created_at for p in posts).date()
    if (hi - lo).days > 400:
        lo = hi - timedelta(days=400)
    return [_day(lo + timedelta(days=i)) for i in range((hi - lo).days + 1)]


def build(posts, assign, narratives, groups, origins, topic: str, since: Optional[datetime], until: Optional[datetime]) -> dict:
    days = _days_between(since, until, posts)
    base = topic_terms(topic) or [topic.lower()]
    TOG = "all terms together"
    terms = base + ([TOG] if len([t for t in base if not t.startswith("#")]) > 1 else [])
    hit = lambda t, x: all(matches_topic(x, b) for b in base if not b.startswith("#")) if t == TOG else matches_topic(x, t)
    plats = sorted({p.platform for p in posts})
    by_day: Dict[str, Counter] = {d: Counter() for d in days}
    term_day: Dict[str, Counter] = {t: Counter() for t in terms}
    term_pl: Dict[str, Counter] = {t: Counter() for t in terms}
    term_acc: Dict[str, set] = {t: set() for t in terms}
    term_posts: Dict[str, List[int]] = {t: [] for t in terms}
    day_term: Dict[str, Counter] = defaultdict(Counter)
    nar_day: Dict[int, Counter] = defaultdict(Counter)
    nar_term: Dict[int, Counter] = defaultdict(Counter)
    for i, p in enumerate(posts):
        d = _day(p.created_at)
        if d in by_day:
            by_day[d][p.platform] += 1
            if assign[i] >= 0:
                nar_day[assign[i]][d] += 1
        for t in terms:
            if hit(t, p.text):
                term_day[t][d] += 1
                term_pl[t][p.platform] += 1
                term_acc[t].add(p.account)
                term_posts[t].append(i)
                day_term[d][t] += 1
                if assign[i] >= 0:
                    nar_term[assign[i]][t] += 1
    n = len(posts)
    day_rows = []
    for d in days:
        c = by_day[d]
        day_rows.append({"date": d, "total": sum(c.values()), "by_platform": {p: c.get(p, 0) for p in plats},
                         "by_term": {t: day_term[d].get(t, 0) for t in terms}})
    term_rows = []
    for t in terms:
        pst = term_posts[t]
        term_rows.append({"term": t, "kind": _kind(t), "posts": len(pst), "share": round(len(pst) / n, 3) if n else 0, "accounts": len(term_acc[t]),
                          "by_platform": {p: term_pl[t].get(p, 0) for p in plats}, "by_day": {d: term_day[t].get(d, 0) for d in days},
                          "first": min((posts[i].created_at for i in pst), default=None) and min(posts[i].created_at for i in pst).isoformat(),
                          "last": max((posts[i].created_at for i in pst), default=None) and max(posts[i].created_at for i in pst).isoformat()})
    nar_rows = []
    for nar in narratives:
        if nar["id"] < 0:
            continue
        nar_rows.append({"id": nar["id"], "label": nar["label"], "posts": nar["posts"],
                         "by_day": {d: nar_day[nar["id"]].get(d, 0) for d in days},
                         "by_term": {t: nar_term[nar["id"]].get(t, 0) for t in terms},
                         "by_platform": nar.get("volume_by_platform") and {p: sum(v.values()) for p, v in nar["volume_by_platform"].items()}})

    # ------------------------------------------------------------- plain-English text
    busiest = max(day_rows, key=lambda r: r["total"]) if day_rows else None
    quiet = [r["date"] for r in day_rows if r["total"] == 0]
    coord_share = round(100 * sum(1 for p in posts if any(p.account in g["accounts"] for g in groups)) / n) if n else 0
    top = sorted((x for x in narratives if x["id"] >= 0), key=lambda x: -x["posts"])
    summary = [f"We looked at '{topic}' from {days[0]} to {days[-1]} on {', '.join(_pl(p) for p in plats)}.",
               f"We found {n:,} posts written by {len({p.account for p in posts}):,} different accounts."]
    if busiest and busiest["total"]:
        summary.append(f"The busiest day was {busiest['date']} with {busiest['total']:,} posts." +
                       (f" {len(quiet)} day(s) had no posts at all." if quiet else ""))
    for r in term_rows:
        summary.append(f"“{r['term']}” ({r['kind']}) was mentioned in {r['posts']:,} posts ({round(100 * r['share'])}% of everything) by {r['accounts']:,} accounts.")
    if top:
        summary.append(f"People are talking about {len(top)} main things. The biggest is “{top[0]['label']}”, with {top[0]['posts']:,} posts.")
    if groups:
        summary.append(f"We found {len(groups)} group(s) of accounts that seem to work together. Together they wrote about {coord_share}% of all the posts.")
    else:
        summary.append("We did not find any group of accounts that clearly works together.")

    nar_plain = []
    for nar in top:
        r = next(x for x in nar_rows if x["id"] == nar["id"])
        peak = max(r["by_day"].items(), key=lambda kv: kv[1])[0] if any(r["by_day"].values()) else None
        pls = sorted((r["by_platform"] or {}).items(), key=lambda kv: -kv[1])
        kw = ", ".join(nar.get("keywords", [])[:5])
        t = f"{nar['posts']:,} posts from {nar['accounts']:,} accounts talk about: {kw or nar['label']}."
        if pls:
            t += " Mostly on " + " and ".join(_pl(p) for p, _ in pls[:2]) + "."
        if peak:
            t += f" It was loudest on {peak}."
        sh = round(100 * nar.get("coordinated_post_share", 0))
        t += f" {sh}% of these posts come from accounts that seem to work together." if sh else " It looks like normal people talking."
        nar_plain.append({"id": nar["id"], "label": nar["label"], "text": t})

    grp_plain = []
    for g in groups:
        sig = [SIGNALS[k] for k, v in sorted(g.get("signal_coverage", {}).items(), key=lambda kv: -_ratio(kv[1])) if k in SIGNALS and _ratio(v) >= 0.1]
        why = "; ".join(sig[:4]) or "their behaviour matched in several ways"
        grp_plain.append({"id": g["id"], "text": f"Group {g['id']} has {g['size']} accounts that seem to work together. Why we think so: {why}. "
                                                 f"This is a clue, not proof: real friends or fans can also look alike."})

    org_plain = []
    for o in origins:
        spread = o.get("platform_spread") or []
        fa = (o.get("first_accounts") or [{}])[0]
        if not spread and not fa:
            continue
        t = f"It first showed up on {_pl(fa.get('platform', ''))} at {_when(fa.get('at', ''))}, posted by “{fa.get('name') or fa.get('account', '?')}”."
        later = [s for s in spread[1:]]
        if later:
            t += " After that it reached " + ", then ".join(f"{_pl(s['platform'])} {_gap(s['lag_minutes'])}" for s in later[:3]) + "."
        else:
            t += " It stayed on that one platform."
        if o.get("seeding_group"):
            t += f" The first wave of posts came from group {o['seeding_group']}, which suggests it was pushed on purpose."
        elif (o.get("early_wave_coordinated_share") or 0) >= 0.5:
            t += " Most of the first posts came from accounts that seem to work together."
        else:
            t += " The first posts look like ordinary users."
        org_plain.append({"narrative_id": o["narrative_id"], "label": o["label"], "text": t})

    return {"days": day_rows, "terms": term_rows, "narratives": nar_rows, "platforms": plats,
            "plain": {"summary": summary, "narratives": nar_plain, "groups": grp_plain, "origins": org_plain}}
