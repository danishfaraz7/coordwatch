"""Pure-stdlib text utilities: normalisation, shingling, MinHash-LSH near-duplicate search, TF-IDF."""
from __future__ import annotations

import math
import random
import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

URL_RE = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"@\w+")
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)  # unicode word chars; drops emoji/punctuation

STOP = set("""a an and are as at be but by for from has have he her his i if in into is it its me my
not of on or our she so than that the their them they this to us was we were what when which who will
with you your just about up out all can do does did been being more most no yes very rt via amp""".split())


def normalize(text: str) -> List[str]:
    """Lowercase, strip URLs/mentions/emoji, return all tokens (stop-words kept)."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = URL_RE.sub(" ", t)
    t = MENTION_RE.sub(" ", t)
    return TOKEN_RE.findall(t)


def content_tokens(tokens: Sequence[str]) -> List[str]:
    return [t for t in tokens if t not in STOP and len(t) > 1]


# ---------------------------------------------------------------- near-duplicates
def _h(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


def shingles(tokens: Sequence[str], k: int = 3) -> frozenset:
    if len(tokens) < k:
        return frozenset([_h(" ".join(tokens))]) if tokens else frozenset()
    return frozenset(_h(" ".join(tokens[i:i + k])) for i in range(len(tokens) - k + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_P = (1 << 61) - 1


class MinHasher:
    def __init__(self, n_perm: int = 64, seed: int = 7):
        rng = random.Random(seed)
        self.ab = [(rng.randrange(1, _P), rng.randrange(0, _P)) for _ in range(n_perm)]

    def signature(self, sh: frozenset) -> Tuple[int, ...]:
        return tuple(min((a * x + b) % _P for x in sh) for a, b in self.ab)


class UnionFind:
    def __init__(self):
        self.p: Dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra

    def groups(self) -> Dict:
        out = defaultdict(list)
        for x in list(self.p):
            out[self.find(x)].append(x)
        return out


def near_duplicate_clusters(token_lists: Sequence[Sequence[str]], threshold: float = 0.7,
                            min_tokens: int = 4, bands: int = 16, rows: int = 4) -> List[List[int]]:
    """Cluster indices whose 3-shingle Jaccard >= threshold. MinHash-LSH for candidate generation,
    exact Jaccard for verification. Returns clusters with >= 2 members."""
    mh = MinHasher(bands * rows)
    sh = [shingles(t) if len(t) >= min_tokens else frozenset() for t in token_lists]
    buckets: Dict[tuple, List[int]] = defaultdict(list)
    for i, s in enumerate(sh):
        if not s:
            continue
        sig = mh.signature(s)
        for b in range(bands):
            buckets[(b, sig[b * rows:(b + 1) * rows])].append(i)
    uf = UnionFind()
    seen = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        if len(members) <= 60:
            pairs = ((members[i], members[j]) for i in range(len(members)) for j in range(i + 1, len(members)))
        else:  # big campaign bucket: chain neighbours; union-find closes the cluster
            pairs = zip(members, members[1:])
        for i, j in pairs:
            if (i, j) in seen:
                continue
            seen.add((i, j))
            if jaccard(sh[i], sh[j]) >= threshold:
                uf.union(i, j)
    return [sorted(v) for v in uf.groups().values() if len(v) >= 2]


# ---------------------------------------------------------------- TF-IDF
SparseVec = Dict[str, float]


class Tfidf:
    def __init__(self, docs: Iterable[Sequence[str]]):
        docs = list(docs)
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vec(self, tokens: Sequence[str]) -> SparseVec:
        tf = Counter(tokens)
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        return normalize_vec(v)


def normalize_vec(v: SparseVec) -> SparseVec:
    n = math.sqrt(sum(x * x for x in v.values()))
    return {k: x / n for k, x in v.items()} if n else {}


def cosine(a: SparseVec, b: SparseVec) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())
