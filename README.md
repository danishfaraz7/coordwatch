# coordwatch — coordinated-activity & misinformation-narrative detection (SOCMINT)

Give it a **topic** (keyword / hashtag / person / brand / event), a **date range** and **2–3 platforms**.
It returns:

| Required output | Where |
|---|---|
| Posts (text, photos, videos, date, engagement, link) | `posts.csv`, `results.json → posts`, HTML table |
| Main narratives, grouped, volume over time + per platform | `narratives.csv`, `volume_by_platform.csv`, HTML charts |
| Groups of accounts that act together, **with the reason for each** | `coordinated_groups.csv`, HTML "Groups of accounts acting together" |
| Where each narrative started: first accounts/posts + cross-platform spread | `origins.csv`, HTML "Where each narrative started" |
| JSON / CSV export + simple dashboard | `out/<run>/results.json`, `*.csv`, `report.html` (self-contained, works offline) |

Core analysis is **pure Python standard library** (no numpy/sklearn) so it installs and runs anywhere in a live demo.

---------------------------------------------------------------------------------------------------

## 0. Web app (one place for every platform)

```bash
pip install requests Pillow telethon      # optional extras for live collection
python -m coordwatch web                  # -> http://localhost:8000
```
Pick a topic + dates + platforms, press **Analyse**. The result is an interactive **constellation**: the topic is the glowing core,
narratives orbit it (gold beams, thickness = volume, red = pushed by coordinated accounts), coordinated groups are purple orbs linked to the
narratives they pushed, and small dots are individual accounts coloured by platform. A time scrubber replays how it spread; click anything for the
detail panel (origin, hops between platforms, evidence); the dock answers simple questions from the data (local rules, **no AI model**).

* **Platforms:** X, YouTube, Telegram are live (official APIs). TikTok / Instagram / Facebook / Snapchat: use the chip to **import an export file**.
  Several sources can be mixed in one run.
* **Start-up & landing:** a short boot animation (dots blink like ordinary accounts, then a few lock into sync - what the tool detects - while real
  connection checks run), then a landing console with live connection chips. Click any key to skip; honours *reduced motion*.
* **Settings (⚙):** one card per service (YouTube, Telegram, X, Gemini) with a status pill and a **Validate** button (cheap metadata calls; keys never leave
  the server except to their own API). Shows connected / key saved / invalid / limited (quota, billing, access) / offline.
* **API keys, once:** ⚙ Settings saves them to `~/.coordwatch/credentials.json` (outside the repo, never returned to the browser).
  Environment variables win, so in **GitHub Codespaces** use *Settings → Codespaces → Secrets* and they are picked up automatically.
* **Optional AI answers (choose your provider):** ⚙ Settings → *AI answers*. Gemini (free tier), Groq, OpenRouter (free Qwen models), Qwen/DashScope, Mistral,
  Cerebras, xAI Grok, **Ollama (local - nothing leaves your machine)**, or any OpenAI-compatible endpoint. Off by default; opt-in with the *AI answers* box.
  Only a *summary* of the run (stats, group reasons, ~8 short quotes, names of the most active public accounts) is sent - never all posts. Posts are treated as
  untrusted data in the prompt, the model has no tools, replies are shown as escaped text tagged *AI-generated*, and keys never go over plain http to a remote host.
  Without it, answers come from local rules. Free tiers and model names change often: use *Validate* to see what your key can reach.
* **Telegram** needs one extra step: `python -m coordwatch telegram-login` (phone + code, once).
* **Codespaces:** *Code → Codespaces → Create*; `.devcontainer/` installs the extras and starts the app on forwarded port 8000 (private).
  (Written from the Codespaces docs, not yet tried in a real Codespace.) Behind a different proxy use `--allow-host <name>`.
* **Safety:** binds to 127.0.0.1 by default; Host-header allow-list, CSRF header + same-origin check on every POST, strict CSP, uploads are extension-checked
  and only parsed as data. Do not expose it to the public internet - there is no login.

## 1. Command line (works offline, 1 second)

```bash
git clone <this repo> && cd coordwatch
python3 -m coordwatch run --topic "Acme Bank" --since 2026-10-01 --until 2026-10-14 \
        --source demo --discount-verified --out out/demo
open out/demo/report.html          # or xdg-open / start
python3 -m unittest discover -s tests -v     # 66 tests
python3 scripts/stress.py                    # accuracy sweep (10 seeds x 5 scenarios)
```

`--source demo` uses a **synthetic** dataset (all accounts/posts fabricated, links use the reserved `.invalid` TLD)
with a *planted* ground truth, so the output also prints precision/recall. A pre-generated example is in `out/example/`.

### Running on real data

```bash
pip install requests Pillow telethon
export X_BEARER_TOKEN=...              # developer.x.com (paid tier)
export YOUTUBE_API_KEY=...             # Google Cloud console, YouTube Data API v3
export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...   # my.telegram.org  (first run asks for a login code)

python3 -m coordwatch run --source live --topic "#AcmeBankCollapse OR Acme Bank" \
        --since 2026-10-01 --until 2026-10-14 --platforms x telegram youtube \
        --telegram-channels @somepublicchannel,@another --out out/live
```

TikTok / Instagram / Facebook / Snapchat have **no usable public research API** for arbitrary keyword search. For those,
collect with your own lawful tooling (e.g. an Apify actor, Bright Data, a vendor export) and import the file:

```bash
python3 -m coordwatch run --source file --input tiktok.json x.csv --file-platform tiktok \
        --topic "Acme Bank" --since 2026-10-01 --until 2026-10-14 --out out/file
```

`fileimport.py` maps common scraper schemas (Apify TikTok/Instagram/Twitter field names, dotted paths, epoch/ISO dates,
CSV/JSON/JSONL). A row only needs `text`, a date, an author and (optionally) engagement counts.

---------------------------------------------------------------------------------------------------

### The dashboard (`report.html`)
Single offline file (no CDN, all scraped text HTML-escaped): dark bento layout with a **streamgraph** of volume per platform,
a clickable **narrative bubble map** (bubble colour = share of posts from coordinated accounts; click filters the posts table),
per-group **link graphs with signal-strength bars and evidence**, and a **spread map** per narrative showing the first appearance on
each platform and the hop delays (e.g. `telegram → x +38m → youtube +26h`).

## 2. Architecture

```
collectors/            (one per platform, all return list[Post])     models.Post  <- common schema
  x.py  youtube.py  telegram.py  fileimport.py  demo.py
  base.py              HttpClient: throttle, retry/back-off, Retry-After, disk cache; avatar dHash
        │
filtering.py           topic (phrases, OR, hashtag-squash) / date / platform / de-dup  (re-applied locally for every source)
        │
narratives.py          TF-IDF -> leader clustering (+2 re-assignment passes, centroid merge) -> labelled narratives
coordination.py        pairwise account evidence -> decision rule -> connected components -> explained groups
origin.py              earliest posts/accounts, per-platform first appearance + lag, copy-paste lineage, seeding verdict
        │
pipeline.py → export.py (JSON, 5 CSVs) + report.py (single-file HTML, inline SVG, no CDN)
evaluate.py + scripts/stress.py   accuracy against planted ground truth
```

## 3. Methodology & design decisions

### Narratives
* Normalise (NFKC, lowercase, strip URLs/@mentions/emoji, keep unicode letters so Arabic/Cyrillic work), drop stop-words, TF-IDF.
* **Leader clustering** in time order, then two re-assignment passes against the final centroids (removes order bias), then
  merging centroids with cosine ≥ 0.30; clusters < 4 posts become "other". Label = top centroid terms excluding the topic words.
* *Why not LLM/embeddings?* Deterministic, free, offline, explainable on a whiteboard, no data leaves the machine. Weakness:
  lexical – paraphrases and other languages cluster poorly (see limitations). The cluster step is one function; swapping in
  multilingual sentence embeddings is the first upgrade I'd make.
* Volume is bucketed hourly (range ≤ 3 days) or daily, total / per narrative / per platform.

### Coordination (the core)
For every pair of accounts I keep **evidence**, not just a score, so each group can be explained to an analyst:

| Signal | Definition | Notes |
|---|---|---|
| `text_dup` | distinct texts both accounts posted, 3-word-shingle Jaccard ≥ 0.70 (MinHash-LSH candidates, exact verification) | reshares excluded; < 4-token posts ignored |
| `sync` | post pairs with similar content < 5 min apart (cosine ≥ 0.55, or ≥ 0.25 if same narrative and < 2 min) | counts distinct post pairs |
| `amplify` | reshares/forwards between the two accounts | |
| `avatar` | profile photo perceptual-hash Hamming ≤ 6/64 | **default avatars excluded** (hash used by > 15 % of accounts or platform flag) |
| `created` | created within 72 h of each other **and** both < 120 days old when first seen | added after the stress test found chance coincidences among old accounts |
| `handle` | same username on different platforms | weak |

**Decision rule (deliberately conservative):** an edge exists if
*strong* – ≥ 2 distinct shared texts, or ≥ 3 sync pairs, or ≥ 3 reshares – **or** *combo* – one content hit (1 shared text / ≥ 1 sync) plus one
identity/network hit (avatar, created, handle, amplify). Edges → connected components → groups of ≥ 3 accounts. Consequences:
a viral meme everyone copied once never forms a group; a shared default avatar is never evidence; creation date alone is never evidence.
Group score = noisy-OR of signal weights × how many of the group's links carry that signal (→ high / medium / low).
Every group lists human-readable reasons plus evidence (the copy-pasted text, closest synchronous post pairs, member list, link graph).

### Origin tracing
Per narrative: earliest post, first 5 distinct accounts, first appearance and lag **per platform**, lineage of the most-copied text across platforms,
and a seeding verdict ("x % of the first 10 % of posts came from coordinated group Gn").

### Tools / libraries / APIs
Python 3.13 stdlib (`re`, `zlib`, `datetime`, `csv`, `json`, `unittest`); **optional**: `requests`, Pillow (dHash of avatars), Telethon.
APIs: X API v2 search, YouTube Data API v3 (search/videos/commentThreads/channels), Telegram MTProto via Telethon, file import for the rest.
No third-party analysis libraries: MinHash-LSH, TF-IDF, union-find, dHash are ~150 lines in `textutil.py` / `collectors/base.py`.

## 4. Rate limits, blocking & platform restrictions
* `HttpClient`: minimum interval between calls, exponential back-off with jitter on 429/5xx, honours `Retry-After` and X's `x-rate-limit-reset`,
  gives up after N tries with a clear message and **keeps the partial results** of other platforms (the report then carries a "BLOCKED/INCOMPLETE" warning).
* Responses are cached on disk (`.cache/`), so re-running a demo costs zero quota; YouTube `search.list` (100 units) is capped by `max_videos`.
* Telegram: `FloodWaitError` → sleep the requested seconds; private channels → `PlatformBlocked`.
* **401/403 are never retried and I do not attempt to bypass blocks** – no proxies rotation, fingerprint spoofing, login-wall scraping or fake accounts.
  Official APIs or user-supplied exports only; the access tier a platform gives is reported as a limitation, not engineered around.
* Unit-tested with a fake session (`tests/test_coordwatch.py::RateLimitTests`).

## 5. How I used AI, and how I checked it
* **Used:** Claude (via Claude Code) wrote the first version of most modules, the synthetic-data generator, tests, and this README under my direction;
  I specified the signals, decision rule and the "no evasion" constraint.
* **Checked – not trusted:**
  1. **Planted ground truth.** The generator labels every account/post, so detection is scored (`evaluate.py`), not eyeballed.
  2. **The first run was wrong, and that's how problems were found:** precision 27 % (a 69-account "group" of organic users) because my organic
     text came from a few templates – real people don't repeat sentences like that, so I made the generator compositional. Campaign B
     (supposed "paraphrase" ring) was actually exact duplicates, so it wasn't a hard test – replaced with grammar-generated paraphrases.
     Narratives were over-fragmented (37 clusters for 9 topics) → threshold sweep.
  3. **Stress test** (10 seeds × 5 scenarios) exposed two real defects: creation-time coincidence among *old* accounts created false groups
     (fixed with the "fresh account" condition), and paraphrase-ring recall of 0.5–0.67 (improved by same-narrative short-window synchrony).
  4. 66 unit tests, including adversarial cases (default avatars, XSS in scraped text, 403 not retried, cache correctness).
  5. API parsers are tested against payloads shaped like the documented responses – **not against live APIs** (no keys in this repo's CI).
     Treat the live collectors as unverified until you run them with your keys.
* **Caveat I want to be explicit about:** I iterated thresholds against my own generator, so the numbers below show the *method's behaviour*, not real-world accuracy.

## 6. Accuracy (synthetic ground truth; `python scripts/stress.py`)

Dataset: ~730 posts / 271 accounts; Campaign A = 28-account copy-paste botnet (4 accounts duplicated across platforms), Campaign B = 6-account
paraphrasing + mutual-reshare ring; decoys = 5 verified newswire outlets, 40-user viral meme, 2 mutually retweeting fans, default avatars.

| scenario (10 seeds, mean (min)) | precision | recall | recall A | recall B |
|---|---|---|---|---|
| default | 0.87 (0.87) | 1.00 (0.97) | 1.00 | 0.98 (0.83) |
| `--discount-verified` | 1.00 | 1.00 (0.97) | 1.00 | 0.98 (0.83) |
| no creation/avatar metadata (Telegram-like) | 1.00 | 1.00 (0.97) | 1.00 | 0.98 (0.83) |
| bots jitter ±2 h | 1.00 | 1.00 (0.97) | 1.00 | 0.98 (0.83) |
| jitter ±2 h **and** no metadata | 1.00 | 0.98 (0.91) | 0.98 (0.89) | 0.98 (0.83) |

**False positives found**
* *Legitimate newswire syndication* – 5 outlets posting the same headline minutes apart look exactly like a botnet. Default run flags them (precision 0.87).
  Mitigation: `--discount-verified` (works only where the platform exposes a verified flag) or an allow-list; in practice an analyst must judge intent.
* Chance coincidences from weak signals (fixed for creation dates; remains possible for `handle`).
**False negatives found**
* Paraphrase ring B: 1–2 of 6 members missed on some seeds (they posted too few synchronous items). Recall B 0.83 at worst.
* A bot who only reshares (never posts original text) gets only `amplify`; it needs ≥ 3 reshares to be caught.
* Not tested and *would* defeat it: paraphrased **and** low-and-slow campaigns, LLM-rewritten text, human-run "coordinated" groups, and cross-platform identity linking beyond identical usernames.

## 7. Limitations & assumptions
* **Not attribution.** Coordination ≠ inauthenticity: fandoms, newsrooms, PR teams, activist campaigns and plain virality produce the same signals. Output = leads for a human analyst.
* Earliest post in *my collected data* ≠ true origin: deleted/suspended accounts, API recency windows (X recent search = 7 days), search ranking limits, and Telegram only seeing channels you list all bias "first".
* Telegram exposes no account-creation date or avatar via the API → those signals unavailable. X avatar hashing needs Pillow + an extra download per account.
* TF-IDF narratives are lexical: weak on paraphrase, sarcasm, mixed-language posts; a single story may split into 2 clusters (seen: "CEO fled" split in two) and merge-thresholds are tuned on English synthetic text.
* Engagement counts are as of collection time and platform definitions differ (X `shares` = retweets+quotes; Telegram `likes` = reactions).
* Photos/videos are recorded as URLs/types; no image/video content analysis (no reverse-image, deepfake or OCR) – natural next step.
* O(n²)-ish in the busiest time windows and in avatar comparison; fine to ~50k posts, beyond that shard by day.
* Privacy: only public content; data stays local; account IDs are shown as collected – handle exports under your data-protection rules.

## 8. Layout
```
coordwatch/            package (web/ (server + constellation UI), collect.py, secrets_store.py, collectors/, narratives.py, coordination.py, origin.py, pipeline.py, report.py, export.py, evaluate.py, cli.py)
tests/                 66 unit tests (unittest; pytest also works)
scripts/stress.py      multi-seed accuracy + ablation table
sample_data/           synthetic posts + ground truth JSON (importable via --source file)
out/example/           pre-generated report, JSON and CSVs
```
