---
name: agent-browser
description: Fast headless CLI browser for all web tasks — reading pages, scraping, form filling, login flows, complex interactions. Default choice for any web browsing task. Fall back to Scout (browse tool) only if this fails.
metadata:
  requires:
    env: []
  always: false
---

# agent-browser

Fast Rust CLI for browser automation via Chrome DevTools Protocol. **Use this for all web browsing tasks** — reading pages, scraping, form filling, extracting data, navigating complex flows. Use `exec()` to run commands.

Fall back to `browse` (Scout) only when:
- `agent-browser` returns a non-zero exit code or clearly can't handle the task
- The task requires desktop (non-browser) GUI automation

---

## Headed vs Headless

**Always ask User before starting:**
> "Should I open the browser so you can see it (headed), or run it invisibly in the background (headless)?"

- **Headed** (`--headed`) — browser window opens visibly. User can watch, intervene, or take over. Use this by default unless he says otherwise.
- **Headless** (no flag) — invisible background session. Faster, but User can't see or interact.

```bash
exec("agent-browser open https://example.com --headed")   # headed (visible)
exec("agent-browser open https://example.com")            # headless (invisible)
```

---

## Core Workflow

1. **Ask** User: headed or headless?
2. Navigate to URL (with or without `--headed`)
3. Snapshot interactive elements (with refs like `@e1`, `@e2`)
4. Interact using refs
5. Re-snapshot after DOM changes (refs become invalid after navigation/updates)

```bash
exec("agent-browser open https://example.com --headed")   # if headed
exec("agent-browser snapshot -i")          # -i = interactive elements only (recommended)
exec("agent-browser click @e3")
exec("agent-browser fill @e5 'search term'")
exec("agent-browser press Enter")
exec("agent-browser wait --load networkidle")
exec("agent-browser snapshot -i")          # re-snapshot after navigation
exec("agent-browser get text @e12")
```

---

## Key Commands

### Navigation
- `agent-browser open <url>` — navigate to URL
- `agent-browser goto <url>` — alias for open
- `agent-browser close` — shut down browser
- `agent-browser wait --load networkidle` — wait for page to settle
- `agent-browser wait <ms>` — wait duration (e.g. `wait 1000`)
- `agent-browser wait --text "some text"` — wait for text to appear

### Discovery (always snapshot before interacting)
- `agent-browser snapshot -i` — accessibility tree of interactive elements with refs (recommended)
- `agent-browser snapshot` — full accessibility tree
- `agent-browser snapshot --json` — machine-readable JSON output
- `agent-browser screenshot` — capture screenshot
- `agent-browser screenshot --annotate` — screenshot with numbered element labels

### Interaction
- `agent-browser click @e1` — click element by ref
- `agent-browser fill @e2 "text"` — clear and fill input
- `agent-browser type @e2 "text"` — type into element (appends)
- `agent-browser press Enter` — press keyboard key (Enter, Tab, Escape, etc.)
- `agent-browser hover @e3` — hover element
- `agent-browser select @e4 "option"` — select dropdown option
- `agent-browser check @e5` / `agent-browser uncheck @e5` — toggle checkbox
- `agent-browser drag @e1 @e2` — drag element to target
- `agent-browser scroll down 500` — scroll page
- `agent-browser eval 'document.title'` — run JavaScript

### Information Retrieval
- `agent-browser get text @e1` — get element text
- `agent-browser get text body` — get full page text
- `agent-browser get html @e1` — get innerHTML
- `agent-browser get value @e1` — get input value
- `agent-browser get attr @e1 href` — get attribute
- `agent-browser get url` — current URL
- `agent-browser get title` — page title

### Finding Elements (semantic, no CSS needed)
- `agent-browser find role button "Submit"` — by ARIA role
- `agent-browser find text "Sign in"` — by text content
- `agent-browser find label "Email"` — by label
- `agent-browser find placeholder "Search..."` — by placeholder
- `agent-browser find testid "submit-btn"` — by data-testid

### Advanced
- `agent-browser set viewport 1920 1080` — set window size
- `agent-browser set device "iPhone 14"` — emulate device
- `agent-browser cookies` — manage cookies
- `agent-browser storage local` — manage localStorage
- `agent-browser screenshot --full` — full-page screenshot
- `agent-browser pdf /tmp/page.pdf` — save as PDF
- `agent-browser console` — get console output
- `agent-browser errors` — get page errors
- `agent-browser diff screenshot --baseline base.png` — visual diff

---

## Authentication

**agent-browser uses its OWN bundled Chromium — not your system Chrome.** Your existing browser logins do not carry over. Sessions only persist when a named `--profile` is used.

### Rule: always use `--profile main` — one unified profile for everything

```bash
exec("agent-browser open https://site.com --headed --profile main")
```

Use **one profile (`main`) for all sites** — LinkedIn, GitHub, Gmail, everything. All logins accumulate in this single profile, exactly like a real browser. A task that touches multiple sites in one session works seamlessly because all sessions are available simultaneously.

**Never create per-site profiles** (`--profile linkedin`, `--profile github`, etc.) — those are isolated contexts that can't share sessions and will break multi-site tasks.

**First-time login for a new site (one-time setup):**
1. Run: `exec("agent-browser open https://site.com --headed --profile main")`
2. Ask User to log in through the headed window
3. Session is saved to `main` permanently — all future tasks reuse it

**All future sessions:** `--profile main` has all accumulated logins. No re-login needed for any previously-authenticated site.

**If you hit a login wall:** close and retry immediately with `--profile main`. Do NOT attempt to automate the login form — ask User to log in once through the headed window.

### Fallback options

1. **Connect to Scout's Chrome session** (only available while Scout is running, port 9222):
   ```bash
   exec("agent-browser connect 9222")
   ```

2. **Fall back to Scout** if agent-browser can't handle authentication at all:
   ```python
   browse(task="<task with full URL>", launch_browser=True)
   # Scout uses User's real Chrome profile with all logins active
   ```

---

## Fallback to Scout

If agent-browser fails (non-zero exit, CAPTCHA, broken page, login wall it can't handle):

```python
# Hand off to Scout — it uses User's full Chrome profile with all logins
browse(task="<original task with full URL and instructions>", launch_browser=True)
```

---

## Examples

```bash
# Read a page (headed — User can watch)
exec("agent-browser open https://news.ycombinator.com --headed")
exec("agent-browser get text body")

# Scrape with structure (headless — no need to watch)
exec("agent-browser open https://news.ycombinator.com")
exec("agent-browser snapshot --json")   # parse JSON for structured data

# Search flow
exec("agent-browser open https://google.com --headed")
exec("agent-browser snapshot -i")
exec("agent-browser fill @e2 'Python async tutorial'")
exec("agent-browser press Enter")
exec("agent-browser wait --load networkidle")
exec("agent-browser snapshot -i")
exec("agent-browser get text body")

# Form fill
exec("agent-browser open https://example.com/contact")
exec("agent-browser snapshot -i")
exec("agent-browser fill @e3 'User'")   # Name field ref from snapshot
exec("agent-browser fill @e4 'x@y.com'")   # Email field ref
exec("agent-browser fill @e5 'Hello'")     # Message ref
exec("agent-browser click @e8")            # Submit button ref
exec("agent-browser wait --load networkidle")
exec("agent-browser get text body")        # Confirm submission

# Screenshot for evidence
# stdout: "✓ Screenshot saved to C:\Users\..\.agent-browser\tmp\screenshots\screenshot-TIMESTAMP.png"
result = exec("agent-browser screenshot")
path = result.stdout.split("Screenshot saved to")[-1].strip()
send_user_media(path=path)
```

---

## Important Notes

- **Always re-snapshot after navigation** — refs (`@e1`, `@e2`) become invalid after page changes
- **Use `-i` flag** — filters to interactive elements only, cleaner and faster for agents
- **Daemon persists between exec() calls** — Chrome stays running, no need to re-open for each command
- **JSON snapshot for data extraction** — use `snapshot --json` when you need structured/parseable output
- **Re-snapshot after DOM updates** — any click or fill that triggers dynamic content requires a fresh snapshot
