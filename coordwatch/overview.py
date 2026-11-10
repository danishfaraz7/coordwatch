"""Plain-language overview: daily counts, mentions per search term, narratives by day and by term, and simple-English
explanations of groups and origins.  Everything here is derived from the analysed posts (no extra collection)."""
from __future__ import annotations

import re
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


_URL = re.compile(r"https?://\S+|www\.\S+")
_NOISE = re.compile(r"(^|\s)(RT|rt)\s+@\w+:?|@\w+|#\w+|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]+")


def headline(nar: dict, by_id: dict, width: int = 90) -> str:
    """A readable one-line gist of a story: the cleaned first sentence of its most representative post."""
    for pid in nar.get("representative_posts") or []:
        p = by_id.get(pid)
        if not p:
            continue
        t = _NOISE.sub(" ", _URL.sub(" ", p.text or ""))
        t = " ".join(t.split()).strip(" -|:·•")
        m = re.match(r"(.{25,}?[.!?])(\s|$)", t)
        t = m.group(1) if m else t
        if len(t) < 12:
            continue
        if len(t) > width:
            t = t[:width].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
        return t[0].upper() + t[1:]
    return ""


def entity_title(texts: list, topic: str = "", fallback_kw: list = None) -> str:
    """A short title built from the people, brands and places the story's posts keep naming (not copied from any one post)."""
    from .trending import terms_from
    skip = {t.lower() for t in topic_terms(topic)} | {topic.lower()}
    names = []
    for t in terms_from([(x, 1) for x in texts if x], top=10):
        term = t["term"]
        if t["kind"] != "phrase" or not 2 <= len(term.split()) <= 3 or term.lower() in skip or any(term.lower() in n.lower() or n.lower() in term.lower() for n in names):
            continue
        names.append(term)
        if len(names) == 3:
            break
    if not names:
        return ""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


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
    by_id = {p.id: p for p in posts}
    for nar in narratives:
        if nar["id"] >= 0:
            nar["gist"] = headline(nar, by_id)
            nar["headline"] = entity_title([by_id[i].text for i in nar.get("post_ids", []) if i in by_id], topic, nar.get("keywords")) or (nar["gist"][:70].rsplit(" ", 1)[0] + "…" if len(nar["gist"]) > 70 else nar["gist"])
    nar_rows = []
    for nar in narratives:
        if nar["id"] < 0:
            continue
        nar_rows.append({"id": nar["id"], "label": nar["label"], "headline": nar.get("headline", ""), "posts": nar["posts"],
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
        b = top[0]
        bp = sorted((b.get("platforms") or {}).items(), key=lambda kv: -kv[1])
        about = f"“{b['headline']}”" if b.get("headline") else f"“{b['label']}”"
        summary.append(f"People are talking about {len(top)} main things. The biggest (Story {b['id']}) is about {about}: {b['posts']:,} posts from {b['accounts']:,} accounts"
                       + (f", mostly on {_pl(bp[0][0])}" if bp else "") + f", {round(100 * b['posts'] / n)}% of everything.")
        if len(top) > 1:
            summary.append("The next biggest: " + "; ".join(f"Story {x['id']} “{x.get('headline') or x['label']}” ({x['posts']:,} posts)" for x in top[1:4]) + ".")
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
        mem = [by_id[i] for i in nar.get("post_ids", []) if i in by_id]
        t = f"{nar['posts']:,} posts from {nar['accounts']:,} accounts"
        if pls:
            t += " (" + ", ".join(f"{_pl(p)} {v:,}" for p, v in pls[:3]) + ")"
        t += "."
        if nar.get("gist"):
            t += f" A typical post says: “{nar['gist']}”."
        if mem:
            first = min(mem, key=lambda x: x.created_at)
            t += f" First seen {first.created_at.strftime('%Y-%m-%d')} on {_pl(first.platform)}."
        if peak:
            t += f" Loudest on {peak} ({r['by_day'][peak]:,} posts)."
        if mem:
            cnt = Counter(x.author_name or x.account for x in mem)
            who, k = cnt.most_common(1)[0]
            t += f" Most active: {who} ({k} post{'s' if k != 1 else ''})."
            eng = sum(x.engagement for x in mem)
            t += f" {eng:,} likes, shares and replies in total."
        if kw:
            t += f" Key words: {kw}."
        sh = round(100 * nar.get("coordinated_post_share", 0))
        t += f" {sh}% of these posts come from accounts that seem to work together." if sh else " No sign of coordination: it looks like normal people talking."
        brief = []
        if mem:
            seen_q, quotes = set(), []
            for x in sorted(mem, key=lambda x: -x.engagement):
                q = " ".join(_URL.sub(" ", x.text or "").split())
                if len(q) >= 25 and q[:40].lower() not in seen_q:
                    seen_q.add(q[:40].lower())
                    quotes.append(f"“{q[:170]}{'…' if len(q) > 170 else ''}” ({x.author_name or x.account}, {_pl(x.platform)}, {x.created_at.strftime('%d %b')})")
                if len(quotes) == 3:
                    break
            last = max(mem, key=lambda x: x.created_at)
            span = (last.created_at - first.created_at).days + 1
            brief = [("What it is about", f"{nar['posts']:,} posts from {nar['accounts']:,} accounts" + (" (" + ", ".join(f"{_pl(p)} {v:,}" for p, v in pls[:3]) + ")" if pls else "")
                      + f" revolve around {nar.get('headline') or kw or nar['label']}. Key words people use: {kw}."),
                     ("In their own words", " ".join(quotes) or "No quotable text."),
                     ("Timeline", f"First seen {first.created_at.strftime('%d %b %Y')} on {_pl(first.platform)}; last seen {last.created_at.strftime('%d %b %Y')} (active over {span} day{'s' if span != 1 else ''})."
                                  + (f" Loudest on {peak} with {r['by_day'][peak]:,} posts." if peak else "")),
                     ("Who is posting", ", ".join(f"{n_} ({c} post{'s' if c != 1 else ''})" for n_, c in cnt.most_common(3)) + f". {nar['accounts']:,} distinct accounts in total."),
                     ("Reach", f"{sum(x.engagement for x in mem):,} likes, shares and replies in total" + (f"; the most engaged post got {max(x.engagement for x in mem):,}." if mem else ".")),
                     ("Coordination check", (f"{sh}% of the posts come from accounts that behave like a group, so treat this story as a lead worth reviewing." if sh else "No sign of coordination: the posts look like independent people reacting."))]
        nar_plain.append({"id": nar["id"], "label": nar["label"], "text": t, "title": nar.get("headline", ""), "brief": brief})

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
