# coordwatch: a plain-language overview

## What is it?
coordwatch is a free tool that looks at what people are posting about a topic on **YouTube, Telegram and X**, and answers three questions:

1. **What is being said?** Posts are grouped into "stories".
2. **Who is saying it, and where did it start?** It shows the first posts and how a story moved from one platform to another.
3. **Are some accounts acting together?** It finds accounts that post the same words, or post within minutes of each other, and shows the evidence.

You type a topic (a word, a hashtag, a person, a brand or an event), choose dates and platforms, and press one button. A few minutes later you have a map, a plain-words summary and downloadable reports.

## Why is it useful?
Fake or pushed-along campaigns often look like normal chatter when you read posts one by one. Seen together, they leave patterns: the same sentence from many accounts, bursts of posts at the same minute, one account's words repeated by others. coordwatch finds those patterns for you, so an analyst, journalist or brand-protection team can check them by hand.

**Important:** it finds leads, not proof. Fan groups, newsrooms and genuinely viral posts can look "coordinated" too. A human decides what the evidence means.

## What do you get?
| Result | Where you see it |
|---|---|
| The posts (text, date, likes, link to the original) | All Posts, `posts.csv` |
| Stories and how big each is over time | What People Say, Map |
| Groups of accounts acting together, with the reasons | Working Together |
| Where each story began and how it jumped between platforms | Where It Started, Across Platforms |
| A short answer in plain words | Summary |
| Reports to share | Web page report, executive PDF, CSV and JSON files |

You can rename any story, and pick which stories go into a report.

## How to use it (5 steps)
1. **Open the app** (setup steps are in `GETTING_STARTED.md`).
2. Click **Try Demo** first. It uses made-up data, so you can see every screen with nothing to connect.
3. For real data: type a topic, pick a short date range (1 to 3 days), tick the platforms, press **Start Investigation**.
4. Read the **Summary**, then look at the **Map** and **Working Together**.
5. Open **Download Results** to get the report.

If nothing matches, the app says so and suggests other searches. It never shows a scary error for that.

## Setup in one minute (easiest way)
Open <https://github.com/danishfaraz7/coordwatch>, click **Code, Codespaces, Create codespace on main**, then in the terminal run:

```
pip install -r requirements.txt
python -m coordwatch web --host 0.0.0.0 --port 8000
```
Click **Open in Browser** when it appears. The full click-by-click guide, including installing on your own computer, is in `GETTING_STARTED.md`.

## What it needs for real data
| Platform | What you need | Cost |
|---|---|---|
| YouTube | a free API key | free |
| Telegram | a free api_id and api_hash and a one-time login | free |
| X | nothing for a small free sample; a Serper key (free sign-up) for more; the paid X API for full coverage | free to paid |

The demo needs nothing.

## Honest limits
* X without the paid API is a **small sample**: text and time only, no likes or replies.
* Telegram free-text search needs a Telegram Premium account; without it, hashtags and channel names carry the search.
* Results depend on what each platform lets the public see.
* It does not read private chats and does not try to get around blocks or logins.

## What it is built with
| Part | Technology | Why |
|---|---|---|
| Core analysis | Python (standard library only) | installs anywhere, easy to review |
| Story grouping | TF-IDF text vectors and clustering | finds posts that talk about the same thing |
| Copy-paste detection | MinHash and similarity search | spots near-identical text quickly |
| Account links | union-find graph, scored evidence | joins accounts into groups with reasons |
| Profile-photo reuse | image hashing (Pillow) | spots many accounts using one picture |
| Collectors | YouTube Data API, Telegram (Telethon), X (API, browser session or public posts), yt-dlp | free routes first |
| Web app | a small Python web server, plain HTML, CSS and JavaScript, canvas map | no heavy framework to install |
| Reports | HTML report, PDF (reportlab), CSV, JSON | easy to read and share |
| Optional AI summary | free Pollinations service, or your own key | off unless you click an AI button |
| Quality | pytest and browser tests (Playwright), run automatically on GitHub | about 160 tests |

Everything runs on your own machine or Codespace. Posts are not sent anywhere. Only if you click an AI button is a short summary (not the posts) sent to the AI service.
