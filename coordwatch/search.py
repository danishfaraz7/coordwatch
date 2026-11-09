"""Natural-language search over one finished run. Local, free, no model download.

Understands plain questions ("youtube posts about refund on 7 nov", "who posted first", "most liked posts from telegram"):
  1. pulls out filters (platform, dates) and intent (earliest / latest / most engaged) from the sentence,
  2. expands the remaining words (stemming + small synonym table + typo tolerance via difflib),
  3. ranks posts, stories, groups and origins with BM25.
"""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

STOP = set("""a an the and or of to in on for with at by from is are was were be been it its this that these those as but not no you your we our
they their he she his her i me my will would can could should may might do does did have has had about than then so if how what when where who whom
why which show give tell find list get all any some there here please posts post tweets tweet videos video comments messages about regarding around""".split())
SYN = {"fake": ["bot", "inauthentic", "spam", "coordinated"], "bot": ["fake", "inauthentic", "spam"], "coordinated": ["campaign", "team", "synchronised", "same"],
       "start": ["origin", "first", "began", "seeded"], "origin": ["start", "first", "seeded"], "spread": ["reached", "shared", "amplify", "reshare"],
       "viral": ["engagement", "likes", "shares"], "angry": ["outrage", "fury", "furious"], "scam": ["fraud", "phishing", "fake"], "money": ["cash", "funds", "savings", "bank"],
       "copy": ["duplicate", "identical", "same"], "team": ["group", "coordinated"], "boost": ["amplify", "reshare", "retweet"]}
PLAT = {"youtube": ("youtube", "yt"), "telegram": ("telegram", "tg"), "x": ("twitter", "x"), "tiktok": ("tiktok",), "instagram": ("instagram", "insta"), "facebook": ("facebook",)}
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_TOK = re.compile(r"#?\w[\w'’]*", re.U)


def stem(w: str) -> str:
    w = w.lower().lstrip("#")
    for suf in ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "ly", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str) -> List[str]:
    return [stem(t) for t in _TOK.findall(text or "") if len(t.strip("#")) > 1 and t.lower() not in STOP]


def parse_query(q: str, today: Optional[datetime] = None) -> dict:
    """Split a sentence into filters, intent and content words."""
    low = " " + q.lower() + " "
    today = today or datetime.now(timezone.utc)
    plat = None
    names = [w for ws in PLAT.values() for w in ws if len(w) > 2]
    for w in re.findall(r"[a-z]+", low):                                           # typo in a platform name: "telegrm", "youtub"
        if len(w) > 4 and w not in names:
            c = difflib.get_close_matches(w, names, n=1, cutoff=0.8)
            if c:
                low = low.replace(w, c[0])
    for p, ws in PLAT.items():
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in ws):
            plat = p
            low = re.sub(r"\b(" + "|".join(map(re.escape, ws)) + r")\b", " ", low)
            break
    day = None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if m:
        day = datetime(int(m[1]), int(m[2]), int(m[3])).date()
        low = low.replace(m[0], " ")
    else:
        m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", low) or \
            re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", low)
        if m:
            a, b = m.groups()
            d, mo = (int(a), MONTHS[b]) if a.isdigit() else (int(b), MONTHS[a])
            try:
                day = datetime(today.year, mo, d).date()
            except ValueError:
                day = None
            low = low.replace(m[0], " ")
        elif " yesterday " in low:
            day = (today - timedelta(days=1)).date(); low = low.replace(" yesterday ", " ")
        elif " today " in low:
            day = today.date(); low = low.replace(" today ", " ")
    sort = None
    if re.search(r"\b(first|earliest|started|start|began|origin|initial|oldest)\b", low):
        sort = "earliest"
    elif re.search(r"\b(latest|recent|newest|last)\b", low):
        sort = "latest"
    elif re.search(r"\b(top|most|viral|popular|liked|shared|viewed|engag\w*|biggest|trending)\b", low):
        sort = "engagement"
    kind = None
    if re.search(r"\b(groups?|team|coordinat\w*|together|bots?)\b", low):
        kind = "groups"
    elif re.search(r"\b(stor(?:y|ies)|narratives?|themes?|topics?|saying|said)\b", low):
        kind = "narratives"
    words = [w for w in tokens(low) if w not in ("first", "earliest", "latest", "recent", "top", "most", "viral", "popular", "liked", "start", "started", "origin", "group", "narrative", "stori", "theme", "topic", "say", "said", "newest", "oldest", "began", "initial", "last", "biggest", "post", "posted", "coordinat", "together", "team", "bot")]
    return {"platform": plat, "day": day.isoformat() if day else None, "sort": sort, "kind": kind, "words": words}


class Index:
    def __init__(self, docs: Dict[str, str]):
        self.tf: Dict[str, Counter] = {k: Counter(tokens(v)) for k, v in docs.items()}
        self.len = {k: sum(c.values()) or 1 for k, c in self.tf.items()}
        self.avg = sum(self.len.values()) / max(1, len(self.len))
        df = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        self.df, self.n = df, max(1, len(self.tf))
        self.vocab = list(df)

    def expand(self, words: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for w in words:
            cands = {w: 1.0}
            for s in SYN.get(w, []) + SYN.get(w + "s", []):
                cands.setdefault(stem(s), 0.5)
            if w not in self.df:                                                   # typo tolerance: kohly -> kohli
                for c in difflib.get_close_matches(w, self.vocab, n=2, cutoff=0.78):
                    cands.setdefault(c, 0.7)
            for t, wt in cands.items():
                out[t] = max(out.get(t, 0), wt)
        return out

    def score(self, key: str, q: Dict[str, float], k1=1.4, b=0.75) -> float:
        tf, s = self.tf[key], 0.0
        for t, wt in q.items():
            f = tf.get(t, 0)
            if f:
                idf = math.log(1 + (self.n - self.df[t] + .5) / (self.df[t] + .5))
                s += wt * idf * f * (k1 + 1) / (f + k1 * (1 - b + b * self.len[key] / self.avg))
        return s


def search(res: dict, query: str, limit: int = 20, today: Optional[datetime] = None) -> dict:
    q = parse_query(query, today)
    posts = res.get("posts", [])
    docs: Dict[str, str] = {}
    for i, p in enumerate(posts):
        docs[f"p{i}"] = f"{p.get('text', '')} {p.get('author_name', '')} {p.get('account', '')} {p.get('platform', '')}"
    for n in res.get("narratives", []):
        docs[f"n{n['id']}"] = f"{n.get('label', '')} {' '.join(n.get('keywords', []))}"
    for g in res.get("coordinated_groups", []):
        docs[f"g{g['id']}"] = f"coordinated group team {' '.join(g.get('reasons', []))} {' '.join(map(str, g.get('accounts', [])))}"
    idx = Index(docs)
    terms = idx.expand(q["words"])

    def keep(p):
        return (not q["platform"] or p.get("platform") == q["platform"]) and (not q["day"] or (p.get("created_at") or "")[:10] == q["day"])

    scored = []
    for i, p in enumerate(posts):
        if not keep(p):
            continue
        sc = idx.score(f"p{i}", terms) if terms else 1.0
        if sc > 0:
            scored.append((sc, i))
    if q["kind"] == "groups" and not terms:
        scored = []
    if q["sort"] == "earliest":
        scored.sort(key=lambda x: (posts[x[1]].get("created_at") or "", -x[0]))
    elif q["sort"] == "latest":
        scored.sort(key=lambda x: (posts[x[1]].get("created_at") or "", x[0]), reverse=True)
    elif q["sort"] == "engagement":
        scored.sort(key=lambda x: (-(posts[x[1]].get("engagement") or 0), -x[0]))
    else:
        scored.sort(key=lambda x: -x[0])
    out_posts = [{**{k: posts[i].get(k) for k in ("id", "platform", "author_name", "text", "created_at", "url", "engagement", "narrative_id", "coordinated_group")}, "score": round(s, 2)}
                 for s, i in scored[:limit]]
    nars, groups = [], []
    for n in res.get("narratives", []):
        s = idx.score(f"n{n['id']}", terms) if terms else 0
        if s > 0 and n["id"] >= 0 and (not q["platform"] or q["platform"] in n.get("platforms", [])):
            nars.append((s, n))
    for g in res.get("coordinated_groups", []):
        s = idx.score(f"g{g['id']}", terms) if terms else 0
        if q["kind"] == "groups" and not terms:
            s = 1
        if s > 0:
            groups.append((s, g))
    nars.sort(key=lambda x: -x[0]); groups.sort(key=lambda x: -x[0])
    origins = []
    if q["sort"] == "earliest" or q["kind"] == "narratives":
        keep_ids = {n["id"] for _, n in nars[:5]} or {n["id"] for n in res.get("narratives", []) if n["id"] >= 0}
        origins = [o for o in res.get("origins", []) if o["narrative_id"] in keep_ids][:5]
    bits = []
    if terms: bits.append("about “" + " ".join(q["words"]) + "”")
    if q["platform"]: bits.append("on " + q["platform"])
    if q["day"]: bits.append("on " + q["day"])
    if q["sort"]: bits.append({"earliest": "earliest first", "latest": "newest first", "engagement": "most engagement first"}[q["sort"]])
    return {"query": query, "understood": "Looking for posts " + (", ".join(bits) if bits else "(everything)"), "filters": {k: q[k] for k in ("platform", "day", "sort", "kind")},
            "total_posts": len(scored), "posts": out_posts,
            "narratives": [{"id": n["id"], "label": n["label"], "posts": n["posts"], "platforms": n["platforms"], "first_seen": n["first_seen"]} for _, n in nars[:5]],
            "groups": [{"id": g["id"], "size": g["size"], "confidence": g["confidence"], "reasons": g["reasons"][:3]} for _, g in groups[:5]],
            "origins": [{"narrative_id": o["narrative_id"], "label": o["label"], "first_post": o["first_post"], "verdict": o["verdict"]} for o in origins]}
