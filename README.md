# coordwatch — coordinated-activity & misinformation-narrative detection (SOCMINT)

coordwatch answers one question for a topic you choose: **who is talking about it, what are they saying, and are some of those accounts acting together?**

You give it a **topic** (keyword, hashtag, person, brand or event), a **date range** and **2–3 platforms**. It collects public posts, groups them into narratives,
finds accounts that appear to act in concert (with the evidence for each group), traces where each narrative started and how it jumped between platforms, and
exports everything as JSON/CSV plus an interactive dashboard and a self-contained HTML report.

It is built to run **at zero cost**: every platform has a free route, and paid or official routes are used first only if you have configured them.
Findings are leads for a human analyst, not attribution. Coordination is not the same as inauthenticity (fandoms, newsrooms and plain virality look similar).

**New to the terminal? Follow the click-by-click guide: [GETTING_STARTED.md](GETTING_STARTED.md).**

## Contents
1. [What it can do](#1-what-it-can-do)
2. [Quick start](#2-quick-start)
3. [Connecting the platforms](#3-connecting-the-platforms)
4. [Optional: AI answers](#4-optional-ai-answers)
5. [Running a search](#5-running-a-search)
6. [Reading the results](#6-reading-the-results)
7. [Run logs and debugging](#7-run-logs-and-debugging)
8. [Troubleshooting](#8-troubleshooting) · [Supported systems](#supported-systems)
9. [Command line](#9-command-line-works-offline-1-second) · 10. Architecture · 11. Methodology · 12. Rate limits · 13. AI use · 14. Accuracy · 15. Limitations · 16. Layout

---------------------------------------------------------------------------------------------------

## 1. What it can do

| Required output | What you get | Where |
|---|---|---|
| **Posts** about the topic in the date range | text, photos/videos, date, engagement (likes/shares/replies/views) and a link to each post | `posts.csv`, `results.json`, posts table in the report/app |
| **Narratives** | what is being said, grouped; volume over time, in total and per platform | `narratives.csv`, `volume_by_platform.csv`, charts |
| **Coordinated groups** | accounts that appear to act together, with the reason for each group: same or near-identical text, posts within minutes of each other, accounts created around the same time, reused profile photos, accounts amplifying each other | `coordinated_groups.csv`, "Accounts acting together" |
| **Origin and spread** | for each narrative, the first accounts and posts, the first appearance on each platform and the delay between platforms, and a verdict on whether it was seeded by a coordinated group | `origins.csv`, "Where each narrative started" |
| **Cross-platform correlation** | narratives that live on several platforms and which one led, hourly/daily volume correlation with lead/lag, Telegram posts that link to the collected YouTube videos, near-identical text across platforms, shared URLs/hashtags, and a plain-English summary | `cross_platform.csv`, `cross_platform_summary.txt`, report tile, app overview panel |
| **Exports and dashboard** | JSON and CSV files, a single offline HTML report, and an interactive web app ("constellation": the topic is the core, narratives orbit it, coordinated groups are linked orbs, a time scrubber replays the spread) | run folder / **Export** menu |
| **Web discovery** (optional) | a free DuckDuckGo sweep that finds Telegram channels and web mentions, and the earliest dated mention | report "Web discovery" tile |
| **Run logs** | a secret-free log of every run (what you searched, which route produced the data, errors) that you can export for a date range | Settings → Run logs |

The core analysis uses only the Python standard library, so it installs and runs anywhere.

Platforms: **YouTube, Telegram and X** are live. TikTok, Instagram, Facebook and Snapchat have no public search API, so for those you **import an export file**
(JSON/CSV/JSONL from your own lawful collection, for example an Apify actor) with the platform chip in the app or `--source file`.

---------------------------------------------------------------------------------------------------

## Supported systems
coordwatch is plain Python (3.9 or newer) with no operating-system-specific code, and runs on **Windows 10/11, macOS (Intel and Apple Silicon) and Linux** (including GitHub Codespaces and WSL).

| | Windows | macOS | Linux / Codespaces |
|---|---|---|---|
| Python command | `py` | `python3` | `python3` (Codespaces: `python`) |
| Create environment | `py -m venv .venv` | `python3 -m venv .venv` | `python3 -m venv .venv` |
| Activate it | `.venv\Scripts\activate` | `source .venv/bin/activate` | `source .venv/bin/activate` |
| Install | `pip install -r requirements.txt` | same | same |
| Start the app | `py -m coordwatch web` | `python3 -m coordwatch web` | `python3 -m coordwatch web` |
| Open | <http://localhost:8000> | same | same (Codespaces: Ports tab) |
| Keys are stored in | `C:\Users\<you>\.coordwatch` | `~/.coordwatch` | `~/.coordwatch` |

Notes: all files are read and written as UTF-8, so Arabic, Hindi, emoji and other scripts work on every system, and exported CSVs open correctly in Excel. The optional X browser route additionally needs `python -m playwright install chromium`.
Tests: `python -m pytest -q`.

---------------------------------------------------------------------------------------------------

## 2. Quick start

### Option A: GitHub Codespaces (no local install)
1. Open the repository on GitHub → **Code → Codespaces → Create codespace on main**. The `.devcontainer/` setup installs the dependencies (including the Playwright browser).
2. In the Codespaces terminal:
   ```bash
   cd /workspaces/coordwatch
   python -m coordwatch web --host 0.0.0.0 --port 8000
   ```
3. Open the **Ports** tab, find port 8000 and open its forwarded address (keep it **private**). The app only accepts `localhost` and `*.app.github.dev` hosts; behind another proxy add `--allow-host <name>`.
4. To update later: `cd /workspaces/coordwatch && git pull`, stop the app (Ctrl+C), start it again and hard-refresh the browser.

### Option B: your own machine
```bash
git clone https://github.com/danishfaraz7/coordwatch && cd coordwatch
python3 -m venv .venv && source .venv/bin/activate        # Python 3.9+
pip install -r requirements.txt
python -m playwright install chromium                     # only needed for the X browser route
python -m coordwatch web                                  # -> http://localhost:8000
```

### Try it without any account
Click **Demo** in the app (or `python -m coordwatch run --topic "Acme Bank" --since 2026-10-01 --until 2026-10-14 --source demo --out out/demo`).
The demo uses a synthetic dataset with planted ground truth, so you can see every output before connecting anything.

Run the tests (optional): `python -m pytest -q` (pytest is in requirements.txt) from the repository folder (140 tests; the browser tests need `playwright install chromium` and skip themselves without it).

### Where keys are stored
Settings (the gear icon) saves keys to `~/.coordwatch/credentials.json`, outside the repository, and never sends them back to the browser. Environment variables win over saved values,
so in Codespaces you can instead add them as **Codespaces secrets** (GitHub → Settings → Codespaces → Secrets) and they are picked up automatically. The Telegram login session
(`~/.coordwatch/telegram.session`) is as sensitive as a password: never commit or share it. In Codespaces, `~/.coordwatch` lives as long as that codespace does.

---------------------------------------------------------------------------------------------------

## Expected output → where to find it

| Expected output | In the app | In the exports / report |
|---|---|---|
| Summary before exporting: posts per day, mentions per keyword / hashtag / person / brand / event, all in simple words | **Dashboard** (opens first after a run) | `daily_counts.csv`, `term_mentions.csv`, `plain_summary.txt`, `overview.json`, report "In plain words / Posts per day / Mentions per keyword" |
| Posts about the topic in the date range, with text, photos, videos, date, engagement and link | **Posts Explorer** (search, platform/theme/group/media filters, thumbnails, open original) | `posts.csv` (text, photo_urls, video_urls, created_at, likes, shares, replies, views, url), `results.json`, report section "Posts" |
| Main narratives, grouped, with volume over time and per platform | **Narratives** with three views: by theme, by date and by keyword/hashtag/person/brand | `narratives.csv`, `volume_by_platform.csv`, `narrative_by_day.csv`, `narrative_by_term.csv`, report "Main narratives" and "day by day and term by term" |
| Groups of accounts acting together, with the reason | **Coordinated Groups** (reasons and signal strength per group, plus a simple-words explanation) | `coordinated_groups.csv` (reasons, accounts), report "Accounts acting together / Why they're grouped" |
| Where each narrative started and how it spread | **Origin & Spread** (a plain story per narrative) and **Cross-Platform** | `origins.csv` (first account, first post, platform order, seeding group), `cross_platform.csv`, report "Where each narrative started" |
| JSON or CSV export and a simple dashboard / HTML report | **Exports** menu, Settings → Run logs | `results.json`, all CSVs, self-contained `report.html` (works offline) |

Group reasons cover: identical or near-identical text, posting within minutes of each other, accounts created around the same time, reused profile photos and accounts amplifying each other. `tests/test_requirements.py` checks every row of this table against a full run.

## 3. Connecting the platforms (API keys, step by step)

**How the keys get into the app.** Every key goes in the same place:
1. Start the app (see [GETTING_STARTED.md](GETTING_STARTED.md)) and open it in your browser.
2. Click the **⚙ gear icon** at the top right. A **Settings** window opens with one card per service (YouTube, Telegram, X, AI).
3. Click into the box on the card, paste the value, and click **Save & validate**. The card shows a status: `connected` (works), `key saved` (stored, not yet checked), `invalid key`, `limited` (quota or access) or `offline`.
4. Click **Done**. You never have to enter a key twice: it is stored in a private file on your computer (`~/.coordwatch/credentials.json`, in your home folder, outside the project) and is never shown again or sent anywhere except to that service.

You do **not** need every key. Minimum useful setup: **the YouTube key** (5 minutes). Telegram is optional but valuable. X is optional and usually skipped.
Tip: copy keys with a normal copy/paste. Do not add spaces, quotes or line breaks around them.

### 3.1 YouTube: free API key
Each platform tries its routes in order. Without a key YouTube falls back to `yt-dlp`, but YouTube usually blocks cloud computers like Codespaces, so get the key.

1. Open <https://console.cloud.google.com/> and sign in with any Google account. (If asked to accept terms, accept. You are **not** asked for a credit card for this.)
2. At the top of the page click the **project selector** (it may say "Select a project") → **New project** → give it any name such as `coordwatch` → **Create**. Wait a few seconds, then make sure that project is selected at the top.
3. Open the left-hand menu (☰) → **APIs & Services** → **Library**.
4. In the search box type `YouTube Data API v3`, click the result, then click the blue **Enable** button.
5. Left menu → **APIs & Services** → **Credentials**.
6. Click **+ Create credentials** → **API key**. A box shows your key (a long string starting with `AIza`). Click the copy icon.
7. (Recommended) Click **Edit API key** → under *API restrictions* choose **Restrict key** → tick **YouTube Data API v3** → **Save**.
8. In coordwatch: **⚙ → YouTube card → paste the key into the "API key" box → Save & validate**. Wait for `connected`.

*Free limit:* 10,000 units per day, resetting at midnight Pacific time. A video search costs 100 units and coordwatch searches roughly once per day of your range, so short ranges cost little. If you see "quota exceeded", wait for the reset or shorten the range.
*Safety:* anyone with the key can use your quota. Do not post it publicly. If it leaks, delete it in the same Credentials page and create a new one.

### 3.2 Telegram: free API login
| Route | Needs | What it does |
|---|---|---|
| 1. Telegram API via Telethon (**recommended**) | free `api_id` and `api_hash`, plus a one-time login | with **no channels entered**: public post/hashtag search, then a channel-directory lookup, then global search; with channels entered: only those |
| 2. Web preview (`t.me/s/...`) | nothing | reads only channels you name (or that web discovery finds); newest few dozen messages per channel; no reactions or groups |

Telegram has no real "search everything" for ordinary accounts, so coverage depends on the route. Use a **spare phone number / Telegram account**, not your main one: automated searching is a grey area of Telegram's terms and the account can be limited.

**Step A: get `api_id` and `api_hash`**
1. Open <https://my.telegram.org> in your browser.
2. Enter the spare account's phone number **with country code** (for example `+919999999999`) → **Next**.
3. Telegram sends a login code **inside the Telegram app** (not SMS). Type it in → **Sign In**.
4. Click **API development tools**.
5. If this is your first time you see a form. Fill **App title** (any name, e.g. `coordwatch`) and **Short name** (5–32 letters/digits, e.g. `coordwatch1`). Leave URL empty. Platform: choose **Other** (or Desktop). Click **Create application**. (If you see an error here, retry later, or from a different network; this page is sometimes fussy.)
6. The next page shows **App api_id** (a number) and **App api_hash** (32 letters and digits). Keep this page open.

**Step B: put them into coordwatch**
7. In coordwatch: **⚙ → Telegram card**. Paste the number into the **api_id** box and the long string into the **api_hash** box → **Save & validate**.

**Step C: log in once (this is a terminal command)**
8. Open a terminal in the project folder (Codespaces: the Terminal panel at the bottom; Windows: PowerShell; Mac: Terminal; remember to activate the virtual environment as in [GETTING_STARTED.md](GETTING_STARTED.md)). If the app is running, open a **second** terminal.
9. Run:
   - Codespaces / Mac / Linux: `python -m coordwatch telegram-login` (use `python3` if `python` is not found)
   - Windows: `py -m coordwatch telegram-login`
10. It asks `Please enter your phone`: type the number with country code, press Enter.
11. It asks for the code: type the code Telegram sent to that account's Telegram app, press Enter. (If the account has two-step verification it also asks for that password.)
12. It prints `Logged in as ... session saved`. The login is stored in `~/.coordwatch` (treat it like a password; never share or commit it).
13. Stop and restart the app. Open **Settings**; the Telegram card should say `connected` or `key saved`. In a run log the credentials line shows `Telegram login: done`.

**Optional checks:**
* `python -m coordwatch tg-search "#yourtag" --days 3` shows what each Telegram search route finds (prints results in the terminal).
* `python -m coordwatch tg-probe @chan1 @chan2` tells you whether named channels are readable and whether they posted recently (ACTIVE / STALE / UNUSABLE).

Hashtag searches on Telegram attract promo/crypto bots that append trending hashtags to templated posts. They appear as genuine coordinated clusters but can crowd out human posts: add phrase terms to the topic (see [Topic syntax](#topic-syntax)).

### 3.3 X (Twitter): optional, usually skipped
X offers no free search API, so X is the hardest platform. You have two routes; if you have neither, **leave X unticked** and use YouTube + Telegram.

**Route 1: official paid API (cleanest)**
1. Open <https://console.x.com> (the X developer portal) and sign in with an X account.
2. Create an app/project and add API credits (paid). Search needs credits; recent search covers the last 7 days.
3. Open your app → **Keys & Tokens** → **Bearer Token** → generate/copy it.
4. In coordwatch: **⚙ → X card → paste into "Bearer token" → Save & validate**. (X is not validated automatically because a check can use paid quota; click Validate yourself.)

**Route 2: free browser session (experimental, against X's terms)**
Uses a *throwaway* X account's own logged-in session; the account can be limited or suspended. Use only an account you can lose.
1. In Chrome or Edge, log in to x.com with the throwaway account.
2. Install a cookie-export extension (for example **Cookie-Editor**). On x.com open it → **Export → JSON**. Save the file somewhere safe, such as `C:\Users\you\x_cookies.json` or `~/x_cookies.json`. Never share this file.
3. Tell the app where it is, by setting `X_COOKIES_FILE` before starting the app:
   * Codespaces: add a **Codespaces secret** named `X_COOKIES_FILE` pointing at the file's path, or run `export X_COOKIES_FILE=/workspaces/x_cookies.json` in the terminal, then start the app in that same terminal.
   * Mac/Linux: `export X_COOKIES_FILE=~/x_cookies.json` then `python3 -m coordwatch web`
   * Windows PowerShell: `$env:X_COOKIES_FILE="$HOME\x_cookies.json"` then `py -m coordwatch web`
   * Command line: add `--x-cookies path/to/x_cookies.json` to `coordwatch run`.
4. The browser route needs Playwright's browser, installed once with `python -m playwright install chromium` (`py -m playwright install chromium` on Windows).

### 3.4 TikTok, Instagram, Facebook, Snapchat (import only)
There is no public research API for keyword search. Collect data with your own lawful tooling (for example an Apify actor or a vendor export) and import the file:
in the app, click the platform's **chip in the toolbar** → choose the file (JSON, JSONL or CSV). A row only needs `text`, a date and an author; engagement counts are optional.
On the command line: `python -m coordwatch run --source file --input tiktok.json --file-platform tiktok --topic "..." --since 2026-10-01 --until 2026-10-14`.

### 3.5 Optional: web discovery (no key)
The CLI flag `--discover`, and the automatic discovery in the app, run a free DuckDuckGo sweep (`site:t.me`, `site:youtube.com`, `site:x.com`, news). It finds Telegram channels when you gave none and no Telegram login exists, lists web mentions and shows the earliest dated mention. These are leads only and never count as coordination evidence.

### 3.6 Using environment variables instead of Settings (optional)
Instead of typing keys into Settings you can provide them as environment variables (they take priority over saved ones): `YOUTUBE_API_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `X_BEARER_TOKEN`, `X_COOKIES_FILE`, `AI_API_KEY`.
In **GitHub Codespaces** the easiest way is *GitHub → Settings → Codespaces → Secrets → New secret* (select the repository), then restart the codespace.

---------------------------------------------------------------------------------------------------

## 4. Optional: AI answers

The dock in the app answers questions about a finished run using local rules, with **no AI model**. You can additionally enable AI answers (off by default). Pick **one** provider:

| Provider | Free? | Where to get the key |
|---|---|---|
| Google Gemini | free tier | <https://aistudio.google.com/apikey> → sign in → **Create API key** |
| OpenRouter (free Qwen models) | free models available | <https://openrouter.ai> → sign up → **Keys → Create key** |
| Groq | free tier | <https://console.groq.com/keys> → **Create API Key** |
| Ollama | free, runs on your own machine, nothing leaves it | install from <https://ollama.com>, no key |

**Step by step (example: OpenRouter + Qwen)**
1. Go to <https://openrouter.ai>, sign up (Google or email), open **Keys** (<https://openrouter.ai/keys>) → **Create key**. Name it `coordwatch`. Set a small **credit limit** (such as $1) so it can never spend more. Copy the key (starts with `sk-or-`); it is shown once.
2. In coordwatch: **⚙ → AI answers card**. In **Provider** choose **OpenRouter**. Paste the key. In **Model** enter a model name that ends in `:free` (free model names change; the model box suggests names after you validate).
3. Click **Save & validate**; wait for `connected`.
4. Close Settings, run an analysis, then tick the **AI answers** checkbox in the question dock and ask something like "which group is most suspicious and why?".

Free-tier limits are low (about 20 requests per minute and a small daily allowance until you add credits), which is plenty for occasional questions. For Gemini and Groq the steps are the same: choose the provider, paste the key, Save & validate.

Only a *summary* of a run (statistics, group reasons, a few short quotes, names of the most active public accounts) is sent, never all posts. Posts are treated as untrusted data in the prompt, the model has no tools, replies are shown as escaped text tagged *AI-generated*, and keys are never sent over plain http to a remote host.

---------------------------------------------------------------------------------------------------

## 5. Running a search

1. Enter the **topic**, the **date range** (UTC, both days inclusive) and tick the **platforms**.
2. For Telegram, leave the channels box blank to use the search routes above, or enter public channels (`@chan1, @chan2`) to read only those.
3. Choose the depth (quick / standard / deep) if offered, then press **Analyse**. Progress shows per platform; **Minimize** keeps it running and **Abort** stops it. The app follows one run at a time.
4. When it finishes, explore the constellation, open the report, or use **Export** to download any file.

### Topic syntax
Terms are alternatives: a post matches if it contains **any** term. Separate terms with a comma, a semicolon, `|` or the word `OR`.
* `Acme Bank` — a phrase (also matches `#AcmeBank`).
* `MrBeast, #MrBeast` or `MrBeast OR #MrBeast` — either term. (A plain word already matches its hashtag, so the second term is redundant.)
* `#indvsnz, #indiavsnewzealand, india vs new zealand` — hashtags plus a phrase, which helps Telegram search find human posts.
* Terms of 4 characters or fewer (`NFP`, `BTC`, `AI`) match whole words only, so `AI` does not match `said`.
* High-volume topics fill the per-platform cap quickly: keep the date range short (a day or two) for very popular topics.

---------------------------------------------------------------------------------------------------

## 6. Reading the results

* **Constellation (app):** gold beams are narratives (thickness = volume, red = pushed by coordinated accounts), purple orbs are coordinated groups, dots are accounts coloured by platform. Click anything for origin, hops between platforms and evidence. The time scrubber replays the spread.
* **Cross-Platform (app):** maps YouTube and Telegram posts onto each other: for every discussion theme found on both platforms it shows the earliest post from each side and who moved first, and it lists Telegram posts that link to YouTube videos collected in the same run.
* **Menu and layout:** the left menu can be minimised with the ‹ button (remembered), the timeline bar on the left of the Constellation scrubs the date range, and the Legend button opens the colour key. Past investigations are listed on Home and reopen from disk after a restart. The layout adapts from phones to ultrawide screens.
* **Report (`report.html`):** one offline file with a streamgraph of volume per platform, a clickable narrative bubble map, per-group link graphs with signal-strength bars and evidence, a spread map per narrative (for example `telegram → x +38m → youtube +26h`), the cross-platform summary, and the posts table.
* **Exports** (all in the run folder, or the Export menu): `results.json`, `posts.csv`, `narratives.csv`, `volume_by_platform.csv`, `coordinated_groups.csv`, `origins.csv`, `cross_platform.csv`, `cross_platform_summary.txt`, `report.html`, `run_log.txt`.
* **Confidence:** each group is rated high / medium / low from the strength and number of its signals. Treat even "high" as a lead to verify.

---------------------------------------------------------------------------------------------------

## 7. Run logs and debugging

Every run, successful, failed or aborted, writes `run_log.txt`. It records the topic, dates, platforms, depth, channels, which credentials are *set* (never their values), the route that produced each platform's data,
errors, counts and a timestamped timeline. In the app: **Copy run log** on the progress card, **Export → run_log.txt** after a run, or **⚙ Settings → Run logs** to export or copy the logs of every run in a from/to date range as one file.
Share these when something looks wrong. They contain no secrets, but they do contain your search topic.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "No posts matched the topic / date range / platforms" | nothing in the window matched. Widen the dates, simplify the topic, or check the run log for platforms that were skipped |
| YouTube: "confirm you're not a bot" / run stops quickly | YouTube refuses datacentre IPs (Codespaces) on the no-key route. Add the free `YOUTUBE_API_KEY` (section 3) |
| YouTube "quota exceeded" | the free 10,000 units/day is used up. Wait for the daily reset (Pacific midnight) or shorten the range |
| Telegram collected 0 posts, "no channels given" | the web preview needs channels. Add the Telegram API login (section 3), or name active channels and vet them with `tg-probe` |
| Telegram "STALE"/dormant channel | the channel has not posted in your window. Pick active channels |
| Telegram searches return crypto/promo bot spam | trending hashtags are being abused. Add phrase terms to the topic; the bots will also appear as a coordinated group |
| Telegram rate limited / "waiting Ns" | Telegram throttles searches; the tool waits automatically. Avoid back-to-back large runs |
| `Telegram login: not done` in the run log | run `python -m coordwatch telegram-login` in a terminal, then restart the app |
| `pytest: command not found` | `pip install pytest`, and run it from the repository folder (`cd /workspaces/coordwatch`) |
| `fatal: not a git repository` | you are in the wrong folder. `cd /workspaces/coordwatch` first |
| App not reachable in Codespaces | start it with `--host 0.0.0.0 --port 8000` and open the forwarded address from the **Ports** tab |
| Changes not showing after `git pull` | restart the app and hard-refresh the browser tab |

---------------------------------------------------------------------------------------------------

## 9. Command line (works offline, 1 second)

```bash
git clone <this repo> && cd coordwatch
python3 -m coordwatch run --topic "Acme Bank" --since 2026-10-01 --until 2026-10-14 \
        --source demo --discount-verified --out out/demo
open out/demo/report.html          # or xdg-open / start
python3 -m unittest discover -s tests -v     # 95 tests
python3 scripts/stress.py                    # accuracy sweep (10 seeds x 5 scenarios)
```

`--source demo` uses a **synthetic** dataset (all accounts/posts fabricated, links use the reserved `.invalid` TLD)
with a *planted* ground truth, so the output also prints precision/recall. A pre-generated example is in `out/example/`.

### Running on real data - zero cost

Every live platform has a free route; if the first route is not configured or is blocked, the next one is tried automatically and the
report's notes say which route produced the data (and why earlier ones were skipped).

| Platform | Route 1 (if configured) | Free route used otherwise | Free-route limits |
|---|---|---|---|
| YouTube | Data API v3 (`YOUTUBE_API_KEY`, free quota) | **yt-dlp** search + top comments, no key | no channel creation date; **cloud/datacentre IPs (e.g. Codespaces) are often refused by YouTube's bot check** - the run then stops with a clear message; use a free API key, a home connection, or `YTDLP_COOKIES_FILE` |
| Telegram | Telethon (`TELEGRAM_API_ID/HASH` + one-time login): public post/hashtag search, channel directory, or your named channels | **t.me/s web preview**, no login | channels you list only (if you list none, web discovery finds some); no reactions/groups |
| X | paid API (`X_BEARER_TOKEN`) | **browser session** (Playwright) with a *throwaway* login: `X_COOKIES_FILE` / `--x-cookies` | experimental, breaks X's ToS, account can be limited/suspended |

```bash
pip install -r requirements.txt && playwright install chromium     # playwright only for the X browser route

python3 -m coordwatch run --source live --topic "#AcmeBankCollapse OR Acme Bank" \
        --since 2026-10-01 --until 2026-10-14 --platforms telegram youtube x \
        --discover --x-cookies ~/x_cookies.json --out out/live
```
Vet channels first: `python -m coordwatch tg-probe @chan1 @chan2` shows whether each is readable and when it last posted (discovery finds name matches, which are often dormant).
`--discover` runs a free DuckDuckGo sweep (`site:t.me`, `site:youtube.com`, `site:x.com`, news): it finds Telegram channels to read when you gave none,
lists web mentions, and shows the earliest dated mention in the report (*Web discovery*). Web mentions are leads only and never count as coordination evidence.
Optional official credentials (set via the web app or env vars) simply take priority: `YOUTUBE_API_KEY`, `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`, `X_BEARER_TOKEN`.

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

## 10. Architecture

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
crossplatform.py       shared narratives, volume correlation + lead/lag, YouTube<->Telegram links, cross-platform copies, summary
        │
pipeline.py → export.py (JSON, 5 CSVs) + report.py (single-file HTML, inline SVG, no CDN)
evaluate.py + scripts/stress.py   accuracy against planted ground truth
```

## 11. Methodology & design decisions

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
APIs/routes: X API v2 (paid) or X web-search JSON via Playwright (free, experimental), YouTube Data API v3 or yt-dlp, Telegram MTProto via Telethon or the t.me/s web preview, DuckDuckGo (`ddgs`) for discovery, file import for the rest.
No third-party analysis libraries: MinHash-LSH, TF-IDF, union-find, dHash are ~150 lines in `textutil.py` / `collectors/base.py`.

## 12. Rate limits, blocking & platform restrictions
* `HttpClient`: minimum interval between calls, exponential back-off with jitter on 429/5xx, honours `Retry-After` and X's `x-rate-limit-reset`,
  gives up after N tries with a clear message and **keeps the partial results** of other platforms (the report then carries a "BLOCKED/INCOMPLETE" warning).
* Responses are cached on disk (`.cache/`), so re-running a demo costs zero quota; YouTube `search.list` (100 units) is capped by `max_videos`.
* Telegram: `FloodWaitError` → sleep the requested seconds; private channels → `PlatformBlocked`.
* **401/403 are never retried and I do not attempt to bypass blocks** – no proxies rotation, fingerprint spoofing, login-wall scraping or fake accounts.
  The one deliberate exception is the **opt-in, off-by-default X browser route**: it uses a throwaway account's own session (against X's ToS) because X has no free API. It still never evades anything - it stops on HTTP 429, a login redirect or an idle timeline and reports why. Every other route uses official APIs, public pages or user-supplied exports; the access a platform gives is reported as a limitation, not engineered around.
* Unit-tested with a fake session (`tests/test_coordwatch.py::RateLimitTests`).

## 13. How I used AI, and how I checked it
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
  4. 95 unit tests, including adversarial cases (default avatars, XSS in scraped text, 403 not retried, cache correctness).
  5. API parsers are tested against payloads shaped like the documented responses – **not against live APIs** (no keys in this repo's CI).
     Treat the live collectors as unverified until you run them with your keys. The free routes (yt-dlp, t.me/s, X browser, DuckDuckGo) are likewise tested only on recorded-shape fixtures and a fake search backend - smoke-test each once on a real machine before the demo.
* **Caveat I want to be explicit about:** I iterated thresholds against my own generator, so the numbers below show the *method's behaviour*, not real-world accuracy.

## 14. Accuracy (synthetic ground truth; `python scripts/stress.py`)

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

## 15. Limitations & assumptions
* **Not attribution.** Coordination ≠ inauthenticity: fandoms, newsrooms, PR teams, activist campaigns and plain virality produce the same signals. Output = leads for a human analyst.
* Earliest post in *my collected data* ≠ true origin: deleted/suspended accounts, API recency windows (X recent search = 7 days), search ranking limits, and Telegram only seeing channels you list all bias "first".
* Telegram exposes no account-creation date or avatar via the API → those signals unavailable. X avatar hashing needs Pillow + an extra download per account.
* TF-IDF narratives are lexical: weak on paraphrase, sarcasm, mixed-language posts; a single story may split into 2 clusters (seen: "CEO fled" split in two) and merge-thresholds are tuned on English synthetic text.
* Engagement counts are as of collection time and platform definitions differ (X `shares` = retweets+quotes; Telegram `likes` = reactions).
* Photos/videos are recorded as URLs/types; no image/video content analysis (no reverse-image, deepfake or OCR) – natural next step.
* O(n²)-ish in the busiest time windows and in avatar comparison; fine to ~50k posts, beyond that shard by day.
* Privacy: only public content; data stays local; account IDs are shown as collected – handle exports under your data-protection rules.

## 16. Layout
```
coordwatch/            package (web/ (server + constellation UI), collect.py, secrets_store.py, collectors/ (incl. youtube_ytdlp, telegram_web, x_browser), discovery.py, narratives.py, coordination.py, origin.py, pipeline.py, report.py, export.py, evaluate.py, cli.py)
tests/                 95 unit tests (unittest; pytest also works)
scripts/stress.py      multi-seed accuracy + ablation table
sample_data/           synthetic posts + ground truth JSON (importable via --source file)
out/example/           pre-generated report, JSON and CSVs
```

### Made for non-technical readers
Plain menu names with tooltips (Summary, Map, What People Say, Accounts Working Together, Where It Started, Download Results), a one-sentence "short answer" on the Summary, big "what to look at next" buttons, jargon-free reasons, a plain-named Download screen covering every export, and a 4-step Help page.

### What's trending
Under the topic box, **See what's trending** lists suggested terms for your dates from the open internet (Google Trends, Google News, GDELT), YouTube (popular videos about the top topics, via yt-dlp) and Telegram (the public channels you list). Each term has **Add to search** and **Copy**. Free, no keys; each source fails on its own with a plain note. `GET /api/trending?since=&until=&channels=`.

### Search and AI summary
**Search Everything** (sidebar) takes plain questions ("most liked youtube posts about refunds", "who posted first", "telegram 7 nov", "coordinated groups") and works across this run or all saved runs, locally and free (`coordwatch/search.py`, `GET /api/search`). The Summary page has an optional **short AI summary** button: it asks first, sends only a compact summary (never all posts), and can use the free no-login Pollinations service or any provider set in Settings → AI.

### Executive PDF and notifications
`executive_report.pdf` is a 2–3 page plain-words report for managers (needs the free `reportlab`: `pip install reportlab`; if it is missing, the Download Results card says so). Data-source warnings (API quota notes, "collected N posts via…") are no longer printed in the HTML/PDF reports; they appear in the 🔔 notifications panel at the top right of the app.
