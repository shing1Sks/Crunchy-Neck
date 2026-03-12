# Browser / Computer Agent — Build Plan

## Context
The main Crunchy Neck agent delegates browser and desktop tasks to this specialized sub-agent that controls a real screen. The parent agent calls a `browse` tool with a task string and mode, and gets back a structured result. Built on **GPT-5.4** with OpenAI's **Responses API** `computer` tool (native CUA), with a strict **260k token cap** to stay below the 272k pricing-doubling threshold. Supports two modes: **browser** (Chrome with persistent profile) and **desktop** (full Windows desktop control).

> **Token pricing note:** For GPT-5.4 (1.05M context window), prompts with >272K input tokens are priced at 2× input and 1.5× output for the full session. We compact at 255k to stay safely below this.

---

## How It Works

```
Parent agent calls: browse("post on LinkedIn about X", mode="browser")
    ↓
ComputerAgent starts, takes screenshot
    ↓
Sends screenshot + task to GPT-5.4 via Responses API (computer tool)
    ↓
GPT-5.4 returns computer_call: { action: "click", coordinate: [450, 320] }
    ↓
PyAutoGUI executes the action, waits 2s for screen to settle
    ↓
New screenshot taken, appended as computer_call_output
    ↓
Loop until model signals DONE / NEED_INPUT / FAILED (or 60 turns max)
```

---

## Folder Structure

```
computer-agent/               ← new folder in project root
├── __init__.py               # exports run_computer_task()
├── agent.py                  # main loop: Responses API + CUA actions
├── browser.py                # Chrome launcher with persistent profile
├── screenshot.py             # PIL ImageGrab → base64 PNG (full screen)
├── actions.py                # PyAutoGUI executor for each action type
├── prompts.py                # system prompts (browser + desktop variants)
├── models.py                 # AgentResult dataclass + ComputerMode type
└── compaction.py             # 260k-cap token compaction for Responses API format
```

Also adds a new `tools/browse/` tool that the parent agent calls.

---

## Mode: browser vs desktop

| Feature | `browser` mode | `desktop` mode |
|---|---|---|
| Chrome launched | Yes (persistent profile) | No (desktop as-is) |
| CUA `environment` | `"browser"` | `"desktop"` |
| Screenshot scope | Full screen (Chrome maximized) | Full screen |
| System prompt | Browser-specific (URL bar, tabs, login flow) | Desktop-specific (apps, Start menu, taskbar, file system) |
| Login handling | NEED_INPUT if not logged in | N/A |
| Session persistence | Chrome user-data-dir | None needed |

Both modes share the same action executor, screenshot logic, compaction, and communication layer.

---

## Requirements

```
pyautogui
pillow
httpx          # Chrome readiness polling
openai         # Responses API (existing dep)
python-dotenv  # existing dep
```

No new API keys — uses existing `OPENAI_API_KEY`. Optional: `CHROME_PATH` env var to override Chrome binary location.

---

## Phase 1 — Core Modules

### computer-agent/models.py
```python
from typing import Literal
from dataclasses import dataclass

ComputerMode = Literal["browser", "desktop"]

@dataclass
class AgentResult:
    status: Literal["done", "failed"]
    deliverable: str | None = None
    reason: str | None = None
```

### computer-agent/screenshot.py
Captures the full screen and returns it as base64 for the Responses API.
- Uses `PIL.ImageGrab.grab()` — same library as `tools/snapshot/snapshot_tool.py`
- Resizes to max **1366×768** to keep vision token cost low
- Returns `(b64_png_str, (width, height))`

### computer-agent/actions.py
Receives a CUA action dict from the model and executes via PyAutoGUI.

**Supported actions:**
- `screenshot` → handled by main loop
- `click` / `double_click` → `pyautogui.click()` / `pyautogui.doubleClick()`
- `type` → `pyautogui.write(text, interval=0.04)`
- `key` / `keypress` → `pyautogui.hotkey(*parts)` or `pyautogui.press(key)`
- `scroll` → `pyautogui.scroll()` at coordinate
- `drag` → `pyautogui.drag()`
- `move` → `pyautogui.moveTo()`
- `wait` → `asyncio.sleep(duration_ms / 1000)`

**Post-action settle delays (slow machine defaults):**
| Action | Delay |
|---|---|
| Default (all) | **2.0s** |
| `click` / `double_click` | **2.0s** |
| `key` with enter/return/tab | **2.5s** (likely navigation) |
| `type` | **1.0s** (input only, no navigation) |
| `wait` | model-specified duration only |
| `screenshot` | **0s** |

Also: `pyautogui.PAUSE = 0.2`, `pyautogui.FAILSAFE = True`

### computer-agent/browser.py
Launches Chrome pointing at a persistent `user-data-dir`. Login state persists automatically.

- Profile stored at `~/.computer-agent/profiles/<name>/user-data`
- Flags: `--remote-debugging-port=9222`, `--user-data-dir=<path>`, `--start-maximized`, `--no-first-run`, `--no-default-browser-check`
- Waits for Chrome via polling `http://127.0.0.1:9222/json/version` (15s timeout)
- Chrome binary search: checks `CHROME_PATH` env var → standard Win32 paths → raises RuntimeError

---

## Phase 2 — System Prompts

### computer-agent/prompts.py

**BROWSER_PROMPT** instructs the model to:
- Control Chrome: address bar, tabs, navigation, scrolling, form filling
- Signal completion:
  - `DONE: <what was accomplished>`
  - `NEED_INPUT: <question for the user>`
  - `FAILED: <reason>`
- For login pages: `NEED_INPUT: Please log in to <site> then type 'done'`
- Never loop on login — if login page reappears after user confirmed, return `FAILED`
- After clicking navigation elements or pressing Enter in URL bar: request screenshot

**DESKTOP_PROMPT** instructs the model to:
- Control the full Windows desktop: Start menu, taskbar, File Explorer, apps
- Open apps via Start menu search or desktop shortcuts
- Use keyboard shortcuts: Win key, Alt+Tab, Win+D, etc.
- Same `DONE/NEED_INPUT/FAILED` signal convention
- No login/session logic

---

## Phase 3 — Main Agent Loop

### computer-agent/agent.py

**API:** OpenAI Responses API

```python
tool_def = {
    "type": "computer",
    "environment": "browser" if mode == "browser" else "desktop",
    "display_width": screen_w,
    "display_height": screen_h,
}
response = client.responses.create(
    model="gpt-5.4",
    tools=[tool_def],
    input=input_list,   # maintained client-side
)
```

**input_list grows as:**
```
[{"role": "user", "content": task_description}]

After each turn:
  → append computer_call item from response.output
  → append {"type": "computer_call_output", "call_id": "...", "output": {
        "type": "computer_screenshot",
        "image_url": "data:image/png;base64,<b64>",
        "detail": "original"
    }}
```

**Loop logic per turn (max 60 turns):**
1. Check token count (excluding base64 blobs) → compact if ≥ 255k
2. Call `client.responses.create(...)`
3. Scan `response.output` items:
   - `type == "computer_call"`:
     - Send `ping_user(update)`: `[browse:{mode}] {action_type}`
     - Execute action via `actions.py`
     - Settle delay
     - Take screenshot
     - Append call + output items to input_list
   - `type == "text"`:
     - Parse for `DONE:` / `NEED_INPUT:` / `FAILED:` prefix
     - `NEED_INPUT` → `ping_user(type="query:msg")` blocks → append user reply as user message → continue (no screenshot this turn)
     - `DONE` / `FAILED` → return `AgentResult`
4. Exhausted turns → `AgentResult(status="failed", reason="Max turns reached")`

**Communication — reuses existing `comm_channels/`:**
```python
from comm_channels.ping_tool import ping_command
from comm_channels.ping_types import PingParams
```
- Live action updates → `type="update"`, `edit_last_update=True`
- User questions (login, OTP) → `type="query:msg"`, blocks until reply

---

## Phase 4 — Token Compaction

### computer-agent/compaction.py

- Estimates tokens by stripping all `data:image/...;base64,<blob>` before counting
- Threshold: **255k tokens** → trigger
- Calls `agent_design.memory_compaction.run_compaction(messages, level="computer")` — the `COMPUTER_COMPACTION_PROMPT` is already implemented in `agent_design/memory_compaction.py`
- Serializes Responses API `input_list` items to text (role messages + action summaries, no base64)
- Rebuilds `input_list` as:
  ```
  [original_task_message, compacted_summary_as_user_msg, last_4_items]
  ```

---

## Phase 5 — Login & Session Management (browser mode only)

### Login Flow (once per profile)
```
Agent navigates to site
→ Screenshot shows login page
→ Model: NEED_INPUT: Please log in to LinkedIn then type 'done'
→ ping_user(type="query:msg") blocks
→ User logs in manually, types 'done'
→ Agent continues with logged-in session
→ Chrome saves login state to user-data-dir
→ Future runs: already logged in, agent proceeds directly
```

### OTP Flow
```
→ Screenshot shows OTP field
→ Model: NEED_INPUT: LinkedIn sent an OTP. Please send me the 6-digit code.
→ ping_user(type="query:msg") blocks
→ User sends "482910"
→ Agent fills the OTP field via type action, continues
```

### Rules
- **Ask for login once per run** — if login page reappears after user confirmed, return `FAILED`
- **No password typing** — agent never has credentials; user handles login manually
- **Google OAuth**: if "Sign in with Google" is visible and Google is already signed in, agent clicks through without blocking; only blocks for manual credential entry
- **Session reuse**: Chrome profile persists; once logged in anywhere, it stays logged in

---

## Phase 6 — Parent Agent Integration

### New tool: `tools/browse/`

Files:
- `tools/browse/__init__.py` — exports `browse_command`, `BrowseParams`, `BROWSE_TOOL`
- `tools/browse/browse_tool.py` — imports `run_computer_task`, calls via `asyncio.run()`
- `tools/browse/browse_types.py` — params + result dataclasses

**Tool schema:**
```json
{
  "name": "browse",
  "description": "Delegate a task to the computer agent. mode='browser' for web/Chrome tasks, mode='desktop' for controlling Windows apps.",
  "parameters": {
    "task":           "string — what to do",
    "mode":           "string (default: 'browser') — 'browser' or 'desktop'",
    "profile":        "string (default: 'default') — Chrome profile (browser mode only)",
    "launch_browser": "boolean (default: true) — launch Chrome (browser mode only)"
  }
}
```

**Existing files to update:**
- `agent_utils/tool_schemas.py` — add `BROWSE_TOOL` to `_CUSTOM_TOOLS`
- `agent_utils/tool_dispatcher.py` — add `elif name == "browse":` dispatch
- `tools/__init__.py` — export `browse_command`, `BrowseParams`, `BROWSE_TOOL`

### computer-agent/__init__.py
```python
from .browser import launch_chrome
from .agent import ComputerAgent

async def run_computer_task(
    task: str,
    mode: str = "browser",       # "browser" | "desktop"
    profile: str = "default",
    launch_browser: bool = True,
    medium: str = "telegram",
) -> dict:
    if mode == "browser" and launch_browser:
        launch_chrome(profile_name=profile)
    result = await ComputerAgent(mode=mode, medium=medium).run(task)
    return {"status": result.status, "deliverable": result.deliverable, "reason": result.reason}
```

---

## Build Order

```
1. computer-agent/models.py + prompts.py                (trivial)
2. computer-agent/screenshot.py + actions.py             (test: screenshot, execute a click)
3. computer-agent/browser.py                             (test: Chrome opens with profile logged in)
4. computer-agent/compaction.py                          (t`est: token estimate, compact at 255k)
5. computer-agent/agent.py                               (test: run("go to google.com"))
6. Desktop mode: adjust prompts.py + mode param          (test: run("open Notepad", mode="desktop"))
7. tools/browse/ + wire into tool_schemas/dispatcher     (test: parent agent calls browse tool)
```

---

## Verification

1. **Basic browser:** `asyncio.run(run_computer_task('Search for Python on Google'))` — Chrome opens, agent searches, returns `DONE`
2. **Login flow:** Navigate to a site requiring login — NEED_INPUT fires via Telegram, user logs in, agent continues
3. **Session reuse:** Run same site again — no NEED_INPUT (session saved in Chrome profile)
4. **Desktop mode:** `run_computer_task("Open Notepad and type hello world", mode="desktop")` — agent controls Windows desktop, no Chrome launched
5. **Compaction:** Long multi-step task that exceeds 255k tokens — verify compaction fires and agent resumes correctly
6. **End-to-end:** Parent agent: `browse("Post a test update on LinkedIn")` → Telegram shows live action updates → result returned to parent

---

## The Login + OTP Flow in Practice

```
Parent: browse("post on LinkedIn: 'Hello world'", mode="browser")
    ↓
Agent navigates to linkedin.com
    ↓
Screenshot shows login page
    ↓
Model: NEED_INPUT: Please log in to LinkedIn. Type 'done' when complete.
    ↓
ping_user blocks → user logs in manually → types 'done'
    ↓
Agent continues with logged-in session
    ↓
Future runs: LinkedIn already logged in, agent proceeds directly
    ↓
OTP case: Model: NEED_INPUT: LinkedIn sent an OTP. Please send me the code.
    ↓
User replies '482910' → agent types the code into the OTP field
```
