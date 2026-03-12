---
name: scout
description: Delegate browser or desktop GUI tasks to Scout — web scraping, form filling, app automation, on-screen data extraction.
metadata:
  requires:
    env: ["OPENAI_API_KEY"]
  always: false
---

# Scout (Computer-Use Subagent)

Scout controls Chrome or the Windows desktop. Use the `browse` tool to delegate tasks
that require clicking, typing into a GUI, reading on-screen content, or navigating
multi-step web flows.

## When to Use

- Scraping content that requires JavaScript rendering or login
- Filling in web forms (job applications, search portals, booking flows)
- Automating desktop apps (Notepad, File Explorer, any Win32 app)
- Extracting structured data from a live webpage
- Any task that says "go to [site] and [do something]"

**Do NOT use Scout for:** tasks exec/read/write can handle directly — git commands,
reading local files, running scripts, anything that doesn't require a GUI.

---

## Tool: `browse`

| Parameter        | Type    | Default    | Description                                           |
|------------------|---------|------------|-------------------------------------------------------|
| `task`           | string  | required   | Full instruction — URL, what to click, what to return |
| `mode`           | string  | "browser"  | "browser" = Chrome; "desktop" = full Windows control  |
| `launch_browser` | boolean | true       | Launch new Chrome before starting                     |
| `max_turns`      | integer | 60         | Loop cap — increase for long flows (e.g. 100)         |

---

## Quick Examples

```python
# Scrape a live page
browse(task="Go to https://news.ycombinator.com and return the top 5 story titles and URLs")

# Fill a form
browse(task="Go to https://example.com/contact, fill Name='Shreyash', Email='x@y.com', Subject='Hello', click Submit, confirm it sent")

# Desktop automation
browse(task="Open Notepad, type 'Hello World', save as hello.txt on the Desktop, then close Notepad", mode="desktop")

# Chrome already open — skip launch
browse(task="Find the LinkedIn Jobs tab and return any open Anthropic roles listed", launch_browser=False)

# Long flow — increase turn cap
browse(task="Go to https://linkedin.com/jobs, search 'AI Engineer', filter Remote, return first 10 results", max_turns=100)
```

---

## What Scout Returns

- **done** → `deliverable`: what was accomplished or data found (plain text summary)
- **failed** → `reason`: why it couldn't complete (CAPTCHA, login wall, wrong page, etc.)

---

## Rules

1. **Give Scout a complete, self-contained task.** Include the exact URL or app name and
   what data to return. Scout has no memory of prior conversations.

2. **browser mode** uses Chrome with a persistent profile — Shreyash's existing logins
   are already active (Gmail, LinkedIn, etc.).

3. **desktop mode** controls the full Windows desktop — can open any app, interact with
   file dialogs, edit documents, use any Win32 GUI.

4. Scout will **ping the user directly** (via ping_user) if it needs a login or OTP.
   After the user responds, Scout continues automatically — Crunchy doesn't need to do
   anything until browse() returns.

5. For long multi-step tasks (>20 distinct steps) set `max_turns=100` or higher.

6. **Send a brief update before calling browse** on any task that'll take more than a
   few seconds:
   ```python
   ping_user(type="update", msg="Launching Scout to scrape LinkedIn jobs...")
   ```

7. **Login retry pattern:** If Scout returns `failed` with a login-related reason, tell
   Shreyash to open that site and log in manually, then retry with `launch_browser=False`.

---

## Progress Updates

Scout sends its own live updates (`[scout] clicked ...`, `[scout] typed ...`) as it works,
so Crunchy doesn't need to forward them. Just send one update when starting a long task and
relay the final deliverable when Scout finishes.
