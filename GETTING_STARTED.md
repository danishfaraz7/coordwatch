# Getting started (no technical experience needed)

This guide takes you from nothing to a running coordwatch, step by step. Copy each command **exactly**, paste it into the terminal and press **Enter**.
You only need a web browser and a free GitHub account for Path A. Path B installs it on your own computer.

**Which path?**
* **Path A: GitHub Codespaces (recommended).** Runs in your browser. Nothing to install. Works the same on Windows, Mac and Linux.
* **Path B: your own computer.** Use this if you prefer to run it locally.

---

## A word about the terminal
A terminal is a window where you type commands. A few things you will see:

| You see | It means |
|---|---|
| `$` at the start of a line | the terminal is waiting for you. **Do not type the `$`**, only the command after it |
| `cd folder` | "go into this folder" |
| `Ctrl+C` | hold **Ctrl** and press **C** to stop a running program |
| pasting | `Ctrl+V` (Windows/Linux), `Cmd+V` (Mac). In the Codespaces terminal you can also right-click → Paste |

If a command prints a red error, do not panic: read the **Fixes** table at the bottom of this page.

---

## Path A: GitHub Codespaces

### Step 1. Get a GitHub account
Go to <https://github.com/signup> and create a free account (skip if you already have one). You must be able to open the project page; if it is private, the owner has to invite you.

### Step 2. Open the project
Go to <https://github.com/danishfaraz7/coordwatch> and sign in.

### Step 3. Create your Codespace
1. Click the green **Code** button.
2. Open the **Codespaces** tab.
3. Click **Create codespace on main**.
4. Wait 2 to 5 minutes. A page that looks like an editor opens. It installs everything by itself the first time.

### Step 4. Open the terminal
At the bottom of the screen there is a **TERMINAL** panel. If you cannot see it: top menu **Terminal → New Terminal**.

### Step 5. Go to the project folder
Type this and press Enter:
```
cd /workspaces/coordwatch
```
The line should now end with `/workspaces/coordwatch (main) $`. If it says "No such file or directory", run `ls /workspaces`, find the folder name it shows, and use that name instead of `coordwatch`.

### Step 6. Make sure everything is installed
```
pip install -r requirements.txt
```
It prints many lines and ends without a red error. (If it says "already satisfied", that is fine.)

### Step 7. Start the app
```
python -m coordwatch web --host 0.0.0.0 --port 8000
```
You should see: `coordwatch web app -> http://localhost:8000`. **Leave this terminal open**, the app is running inside it.

### Step 8. Open the app in your browser
* A small pop-up usually appears: click **Open in Browser**.
* If not: click the **PORTS** tab next to TERMINAL, find port **8000**, and click the small **globe icon** next to its address.

You now see the coordwatch start screen.

### Step 9. Try it with the built-in demo
Click **Demo**. It analyses fake data, so you can see what the results look like before connecting anything.

### Step 10. Stop and restart later
* **Stop the app:** click in the terminal and press `Ctrl+C`.
* **Come back another day:** go to <https://github.com/codespaces>, click your codespace to reopen it, open the terminal and run:
  ```
  cd /workspaces/coordwatch
  git pull
  python -m coordwatch web --host 0.0.0.0 --port 8000
  ```
  (`git pull` downloads the newest version of the tool. After starting, refresh the browser tab with `Ctrl+Shift+R`.)
* A codespace sleeps by itself after about 30 minutes of inactivity and your files are kept. Free GitHub accounts have a monthly hours allowance: at <https://github.com/codespaces> you can **Stop** a codespace you are not using.

---

## Path B: your own computer

### Step 1. Install Python
1. Go to <https://www.python.org/downloads/> and download Python 3.10 or newer.
2. **Windows:** run the installer and **tick "Add python.exe to PATH"** on the first screen, then click Install Now.
   **Mac:** open the downloaded file and follow the installer.
3. Check it worked. Open a terminal (**Windows:** press the Windows key, type `PowerShell`, Enter. **Mac:** press Cmd+Space, type `Terminal`, Enter) and run:
   * Windows: `py --version`
   * Mac/Linux: `python3 --version`

   You should see something like `Python 3.12.1`.

### Step 2. Download the project
1. Open <https://github.com/danishfaraz7/coordwatch>.
2. Click the green **Code** button → **Download ZIP**.
3. Open your Downloads folder, right-click the ZIP and **Extract All** (Windows) or double-click it (Mac). You get a folder named `coordwatch-main`.

### Step 3. Go into the folder
In the terminal:
* **Windows:**
  ```
  cd $HOME\Downloads\coordwatch-main
  ```
* **Mac/Linux:**
  ```
  cd ~/Downloads/coordwatch-main
  ```
If it says the path does not exist, the folder may be nested (`coordwatch-main\coordwatch-main`). Run `dir` (Windows) or `ls` (Mac) to see the contents, then `cd` into the inner folder.

### Step 4. Create a private Python environment (one time)
* **Windows:**
  ```
  py -m venv .venv
  .venv\Scripts\activate
  ```
  If Windows says scripts are disabled, run `Set-ExecutionPolicy -Scope Process Bypass` and then the `activate` line again.
* **Mac/Linux:**
  ```
  python3 -m venv .venv
  source .venv/bin/activate
  ```
The line now starts with `(.venv)`. That means it worked.

### Step 5. Install the requirements (one time)
```
pip install -r requirements.txt
```
Wait until it finishes (a minute or two).

### Step 6. Start the app
```
python -m coordwatch web
```
Open your browser and go to **<http://localhost:8000>**. Click **Demo** to see it working.

### Stop and restart later
* Stop: click the terminal and press `Ctrl+C`.
* Start again another day: open a terminal, `cd` into the folder (Step 3), activate the environment (Step 4, only the `activate` / `source` line), then `python -m coordwatch web`.

---

## Connect real platforms (when you are ready)

The demo needs nothing. For real data, connect the platforms you want. In the app click the **gear icon (⚙) → Settings**.

### YouTube (free key, about 5 minutes) — do this first, it is the most useful
1. Go to <https://console.cloud.google.com/> and sign in with a Google account.
2. At the top click the project selector → **New project** → **Create**.
3. In the left menu: **APIs & Services → Library**. Search **YouTube Data API v3** → click it → **Enable**.
4. **APIs & Services → Credentials → Create credentials → API key**. Copy the key it shows.
5. In coordwatch Settings → **YouTube**: paste the key → **Save & validate**. It should turn green.

### Telegram (free, optional, about 10 minutes)
1. Go to <https://my.telegram.org>, log in with a phone number (use a **spare number/account**, not your main one), open **API development tools**, create an app (any name), and copy the **api_id** and **api_hash**.
2. In Settings → **Telegram**: paste both → **Save**.
3. In the terminal (open a **second** terminal if the app is running: in Codespaces click the **+** in the terminal panel; locally open a new window and repeat Path B steps 3 and 4), run:
   ```
   python -m coordwatch telegram-login
   ```
   Type the phone number with country code (for example `+919999999999`), then the code Telegram sends you. It ends with "session saved".
4. Stop the app (`Ctrl+C`) and start it again.

### X (Twitter)
Needs a paid API token or a spare account, so skip it unless you have one. YouTube + Telegram is enough.

## Run your first real search
1. Topic: something with recent activity, for example `MrBeast` (use commas for several terms: `MrBeast, #MrBeast`).
2. Dates: a short, recent range (1 to 3 days).
3. Tick **YouTube** and **Telegram**. Leave the Telegram channel box empty.
4. Press **Analyse** and wait. When it finishes, open the report and use **Export** to download files.
5. If something looks wrong: **⚙ Settings → Run logs → Export**, and send that file to whoever is helping you. It contains no passwords or keys.

---

## Fixes

| What you see | What to do |
|---|---|
| `command not found: python` | use `python3` instead (Mac/Linux), or `py` (Windows) |
| `No such file or directory` after `cd` | you are in the wrong place. Run `ls` (Mac/Linux/Codespaces) or `dir` (Windows) to see folders and `cd` into the right one |
| `No module named ...` | the requirements are missing: run `pip install -r requirements.txt` again (and activate the environment first on Path B) |
| `fatal: not a git repository` | you are not inside the project folder. `cd /workspaces/coordwatch` |
| `Address already in use` | the app is already running in another terminal. Stop it with `Ctrl+C` there, or restart the codespace |
| The page does not open in Codespaces | open the **PORTS** tab and click the globe icon next to port 8000. Make sure you started the app with `--host 0.0.0.0 --port 8000` |
| The page is old after an update | refresh with `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac) |
| "No posts matched" | widen the dates or simplify the topic |
| YouTube result is empty or blocked | add the YouTube key (above); without it YouTube often refuses cloud computers |
| Telegram returns nothing | do the Telegram steps above, or type public channel names like `@channelname` in the Telegram box |

Exact click-by-click steps for every API key (YouTube, Telegram, X, AI) are in [README section 3](README.md#3-connecting-the-platforms-api-keys-step-by-step). More detail on the results and the method is in the main [README](README.md).
