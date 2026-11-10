Subject: coordwatch: Coordinated Activity and Misinformation Detection (take-home submission)

Hello,

Please find my submission for the Coordinated Activity and Misinformation Detection task.

Repository: https://github.com/danishfaraz7/coordwatch
Start here: the attached Word document (or OVERVIEW.md in the repository) and GETTING_STARTED.md (step-by-step setup for non-technical readers). A ready-made sample report is in out/example/ (open report.html).

The documentation follows. It is written so that a non-technical reader can set the tool up and use it.

## Application purpose
coordwatch is an open source tool that looks at what people are posting about a topic on **YouTube, Telegram and X**, and reports three things:

1. **Content.** Posts are grouped into "stories".
2. **Origin and spread.** The first posts of each story, and how it moved between platforms.
3. **Coordination.** Accounts that post the same words, or post within minutes of each other, with the evidence.

You type a topic (a word, a hashtag, a person, a brand or an event), choose dates and platforms, and press one button. A few minutes later you have a map, a plain-words summary and downloadable reports.

## Value and typical uses
Fake or pushed-along campaigns often look like normal chatter when you read posts one by one. Seen together, they leave patterns: the same sentence from many accounts, bursts of posts at the same minute, one account's words repeated by others. coordwatch finds those patterns for you, so an analyst, journalist or brand-protection team can check them by hand.

**Important:** it finds leads, not proof. Fan groups, newsrooms and genuinely viral posts can look "coordinated" too. A human decides what the evidence means.

## Outputs and results
| Result | Where you see it |
|---|---|
| The posts (text, date, likes, link to the original) | All Posts, `posts.csv` |
| Stories and how big each is over time | What People Say, Map |
| Groups of accounts acting together, with the reasons | Working Together |
| Where each story began and how it jumped between platforms | Where It Started, Across Platforms |
| A short answer in plain words | Summary |
| Reports to share | Web page report, executive PDF, CSV and JSON files |

You can rename any story, and pick which stories go into a report.

## Operating the application
1. **Open the app** (setup steps are below and in GETTING_STARTED.md in the repository).
2. Click **Try Demo** first. It uses made-up data, so you can see every screen with nothing to connect.
3. For real data: type a topic, pick a short date range (1 to 3 days), tick the platforms, press **Start Investigation**.
4. Read the **Summary**, then look at the **Map** and **Working Together**.
5. Open **Download Results** to get the report.

If nothing matches, the app says so and suggests other searches. It never shows a scary error for that.

## Installation
Three ways to run it. Option A needs nothing installed. Options B and C need Python 3.10 or newer (python.org/downloads; on Windows tick "Add python.exe to PATH").

**Option A: GitHub Codespaces (recommended).** Open the repository, click Code, Codespaces, Create codespace on main, wait 2 to 5 minutes, then in the terminal run `cd /workspaces/coordwatch`, `pip install -r requirements.txt` and `python -m coordwatch web --host 0.0.0.0 --port 8000`. Click Open in Browser.

**Option B: Windows.** Install Python, click Code, Download ZIP and Extract All, open PowerShell and run:
```
cd $HOME\Downloads\coordwatch-main
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m coordwatch web
```
Then open http://localhost:8000. If Windows says scripts are disabled, run `Set-ExecutionPolicy -Scope Process Bypass` and activate again.

**Option C: Mac (Linux is the same).** Install Python, click Code, Download ZIP and double-click it, open Terminal and run:
```
cd ~/Downloads/coordwatch-main
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m coordwatch web
```
Then open http://localhost:8000.

To stop, press Ctrl+C in the terminal. To start again, go to the folder, activate the environment, and run `python -m coordwatch web`. Common fixes are in GETTING_STARTED.md.

## Requirements for live data
| Platform | What you need | Cost |
|---|---|---|
| YouTube | a free API key | free |
| Telegram | a free api_id and api_hash and a one-time login | free |
| X | nothing for a small free sample; a Serper key (free sign-up) for more; the paid X API for full coverage | free to paid |

The demo needs nothing.

## Implementation walkthrough
Every collector returns the same simple post record, so the analysis does not care where a post came from.
1. **Collect.** One collector per platform (YouTube, Telegram, X, or an imported file), with throttling, retries and an on-disk cache.
2. **Filter.** Topic, dates and platform are applied again locally; duplicates are removed.
3. **Group into stories.** Text is cleaned, weighted with TF-IDF and clustered in time order. Each story gets a title you can rename.
4. **Detect coordination.** Pairs of accounts are compared on six signals; those that pass the decision rule are joined into groups with reasons and evidence.
5. **Trace origin.** Earliest posts and accounts, first appearance per platform, delay between platforms, and whether a coordinated group seeded the story.
6. **Compare platforms.** Stories on several platforms, which one led, and links between Telegram posts and YouTube videos.
7. **Export and show.** JSON, CSV, a single-file HTML report, an executive PDF, and the interactive web app.

## Methodology and design decisions
* **Deterministic text methods instead of AI embeddings.** Repeatable, free, offline, explainable, and no post data leaves the machine. The cost: paraphrases and mixed languages cluster poorly. Multilingual embeddings are the first upgrade.
* **Six signals per account pair:** copy-pasted text (3-word-shingle similarity 0.70 or more), posting in sync (under 5 minutes apart), reshare loops, reused profile photos, accounts created together (within 72 hours, both under 120 days old), and the same handle across platforms (weak).
* **Conservative decision rule.** Accounts are linked only on strong evidence (2 shared texts, or 3 synchronised pairs, or 3 reshares) or a combination of one content signal and one identity or network signal. Groups need at least 3 accounts and are rated high, medium or low. One weak signal alone never forms a group.
* **Evidence over scores.** Each group lists plain-language reasons, the copied text, the closest synchronised posts and its members, so a person can accept or reject it.

## Tools, libraries and APIs
| Part | Technology | Why |
|---|---|---|
| Core analysis | Python standard library only; own TF-IDF, clustering, MinHash and union-find code | installs anywhere, easy to review |
| Profile-photo reuse | Pillow (image hashing) | spots many accounts using one picture |
| YouTube | YouTube Data API v3; yt-dlp as key-free fallback | official first, free fallback second |
| Telegram | Telethon (official API) and the public t.me web preview | search of public channels |
| X | X API v2 (paid), browser session (experimental), public posts via web search, optional Serper key | free route first, paid optional |
| Discovery and trending | ddgs, Google Trends, Google News, GDELT | suggested search terms, no key needed |
| Web app | small Python web server, plain HTML, CSS and JavaScript, canvas map | no heavy framework |
| Reports | HTML, PDF (reportlab), CSV, JSON | easy to read and share |
| Optional AI summary | free Pollinations service or your own key | off unless an AI button is clicked |
| Quality | pytest and Playwright, run on GitHub for every change | about 160 tests |

Everything runs on your own machine or Codespace. Posts are not sent anywhere.

## Rate limits, blocking and platform restrictions
* **Throttling and retries.** One client with a minimum gap between calls, exponential back-off with jitter on 429 and 5xx, and respect for Retry-After. After a set number of tries it stops with a clear message, keeps partial results and flags the report as incomplete.
* **Caching.** Responses are cached on disk, so repeat runs cost no quota. YouTube search is capped because each search costs 100 quota units.
* **Telegram.** Flood-wait errors make the tool sleep as long as requested. Private channels are skipped and reported. Free-text search needs Premium; otherwise hashtags, channel names and global search are used.
* **No evasion.** 401 and 403 are never retried. No proxy rotation, fingerprint spoofing, login scraping or fake accounts. Access limits are reported as limitations.
* **The one exception.** X has no free API, so an optional, off-by-default browser-session route uses a spare account\u2019s own session. It goes against X\u2019s terms, is labelled experimental, and stops at a rate limit, login redirect or empty timeline. The default free X route reads public posts found through web search.
* **Blocked or missing keys.** YouTube without a key is often blocked on cloud computers, so a free key is recommended. Free AI services are rate limited, so the app waits, shows a countdown and retries.

## Use of AI and how its output was checked
**Where AI was used.** Claude (through Claude Code) wrote the first version of most modules, the synthetic-data generator, the tests and the documentation, under my direction. I specified the signals, the decision rule and the rule against evading platform blocks. Inside the application AI is optional: it runs only when an AI button is clicked, sees a short summary rather than the posts, and its output is labelled AI-generated with numbered references to the source posts.

**How the output was checked, not trusted:**
* **Planted ground truth.** The generator labels every account and post, so detection is scored against known answers.
* **First results were wrong.** Precision was 27 percent because generated normal posts repeated a few templates; the generator was rebuilt for varied text. One planted group was only exact copies and was replaced with paraphrases. Stories were over-split; a threshold sweep fixed that.
* **Stress test.** Ten seeds across five scenarios exposed two real defects: creation-time coincidences among old accounts (fixed with a recent-account condition) and weak recall on paraphrase groups (improved with short-window synchrony inside a story).
* **Automated tests.** About 160, including default avatars, script injection in post text, 403 responses that must not be retried, and cache correctness.
* **Live data.** YouTube and Telegram were run on real topics. X without a key or token remains a small sample.
* **Fixes from real runs.** For example crashes on forwarded Telegram posts and misleading "looks organic" messages on tiny samples.

## Accuracy: false positives and false negatives
Synthetic data: about 730 posts, 271 accounts, a 28-account copy-paste botnet, a 6-account paraphrasing ring and decoys (5 verified news outlets, a 40-user viral meme, two mutually retweeting fans, default avatars). Mean of 10 seeds.

| Scenario | Precision | Recall | Worst recall |
|---|---|---|---|
| Default settings | 0.87 | 1.00 | 0.97 |
| Verified accounts discounted | 1.00 | 1.00 | 0.97 |
| No account-creation or photo data (Telegram-like) | 1.00 | 1.00 | 0.97 |
| Bots vary posting time by up to 2 hours | 1.00 | 1.00 | 0.97 |
| Time variation and no account data together | 1.00 | 0.98 | 0.91 |

**False positives found.** News outlets syndicating one headline minutes apart look like a botnet, so the default run flags them (precision 0.87). Discounting verified accounts or an allow-list removes them, but a person still judges intent. In live runs, paid trading-signal channels copy the same call within minutes: real coordination, but commercial rather than misinformation. Weak signals can coincide by chance; fixed for creation dates, still possible for same-handle matches.

**False negatives found.** In the paraphrasing ring, 1 or 2 of 6 members were missed on some seeds for lack of synchronised posts (recall 0.83 at worst). An account that only reshares needs at least 3 reshares. Not tested and likely to defeat the tool: slow low-volume campaigns that also paraphrase, AI-rewritten text, human-run groups, and identity linking beyond identical usernames.

**Caveat.** Thresholds were tuned against my own generator, so these figures show how the method behaves, not accuracy on real platforms.

## Limitations and assumptions
* Findings are leads for a person to check, not attribution. Fan groups, newsrooms, PR teams and viral posts can produce the same signals.
* X without the paid API is a small sample: text and time only.
* Telegram covers public channels only, free-text search needs Premium, and it exposes no account-creation date or profile photo.
* The earliest post found is not necessarily the true origin: deleted accounts, search ranking and visible channels bias what is "first".
* Story grouping is word-based: weak on paraphrase, sarcasm and mixed languages.
* Engagement counts are as of collection time and mean different things per platform.
* Photos and videos are links only; no image or video analysis.
* Speed is fine up to about 50,000 posts; beyond that, split by day.
* Only public content is collected and data stays on your machine; handle exports under your own data-protection rules.

## Code repository and setup
Repository: https://github.com/danishfaraz7/coordwatch (open source, MIT licence)
* `README.md`: every feature, method, accuracy tests, rate limits, limitations and AI use.
* `GETTING_STARTED.md`: click-by-click setup, API keys, a tour of every screen, common fixes.
* `OVERVIEW.md`: this document. Setup steps are under Installation.
* `out/example/`: a ready-made sample report.
* `tests/` and `scripts/stress.py`: automated tests and the accuracy test.

Thank you for your time. I would be glad to walk through it.

Regards,
Danish Faraz
