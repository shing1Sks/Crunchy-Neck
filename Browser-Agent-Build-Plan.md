Gemini Computer Use Agent — Build Plan

How It Works
Parent agent calls: run_computer_task("post on LinkedIn about X")
        ↓
ComputerAgent starts
        ↓
Takes screenshot of current screen
        ↓
Sends screenshot + task to Gemini computer use model
        ↓
Gemini returns action: { type: "click", x: 450, y: 320 }
        ↓
PyAutoGUI executes the action
        ↓
New screenshot taken
        ↓
Loop until Gemini signals DONE or calls ping_user

Folder Structure
computer-agent/
├── main.py                  # Dev/test entry point
├── .env
├── requirements.txt
│
├── core/
│   ├── agent.py             # Main loop — the brain
│   ├── models.py            # Pydantic schemas
│   └── prompts.py           # System prompt
│
├── executor/
│   ├── __init__.py
│   ├── screenshot.py        # Screen capture
│   ├── actions.py           # PyAutoGUI action executor
│   └── chrome.py            # Chrome launcher with profile
│
└── comms/
    └── user.py              # ping_user — blocks for human input

Requirements
google-genai
pyautogui
pillow
pydantic
pydantic-settings
python-dotenv

Phase 1 — Screenshot + Action Executor
executor/screenshot.py
Captures the full screen and returns it as base64 for Gemini.
pythonimport pyautogui
import base64
from io import BytesIO
from PIL import Image

def take_screenshot() -> tuple[str, tuple[int, int]]:
    """
    Returns (base64_image, (width, height))
    Resizes to max 1366x768 to keep token costs down.
    """
    screenshot = pyautogui.screenshot()
    
    # Resize if too large
    max_w, max_h = 1366, 768
    w, h = screenshot.size
    if w > max_w or h > max_h:
        ratio = min(max_w / w, max_h / h)
        screenshot = screenshot.resize(
            (int(w * ratio), int(h * ratio)), 
            Image.LANCZOS
        )
    
    buffer = BytesIO()
    screenshot.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return b64, screenshot.size
executor/actions.py
Receives Gemini's action output and executes it via PyAutoGUI.
pythonimport pyautogui
import asyncio
import time

# Safety: PyAutoGUI failsafe — move mouse to corner to abort
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3  # small pause between actions

async def execute_action(action: dict) -> str:
    """
    Executes a single Gemini computer use action.
    Returns a string result description.
    """
    action_type = action.get("action")
    
    if action_type == "screenshot":
        # Model is requesting a fresh screenshot — handled by main loop
        return "screenshot_requested"

    elif action_type == "click":
        x, y = action["coordinate"]
        button = action.get("button", "left")
        btn_map = {"left": "left", "right": "right", "middle": "middle"}
        pyautogui.click(x, y, button=btn_map.get(button, "left"))
        return f"clicked ({x}, {y}) with {button} button"

    elif action_type == "double_click":
        x, y = action["coordinate"]
        pyautogui.doubleClick(x, y)
        return f"double-clicked ({x}, {y})"

    elif action_type == "type":
        text = action.get("text", "")
        # Small delay for realistic typing
        pyautogui.write(text, interval=0.04)
        return f"typed: {text[:50]}{'...' if len(text) > 50 else ''}"

    elif action_type == "key":
        keys = action.get("key", "")
        # Handle combos like "ctrl+c", "shift+tab"
        if "+" in keys:
            parts = keys.split("+")
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(keys)
        return f"pressed key: {keys}"

    elif action_type == "scroll":
        x, y = action["coordinate"]
        direction = action.get("direction", "down")
        amount = action.get("amount", 3)
        pyautogui.moveTo(x, y)
        scroll_val = amount if direction == "up" else -amount
        pyautogui.scroll(scroll_val)
        return f"scrolled {direction} at ({x}, {y})"

    elif action_type == "move_mouse":
        x, y = action["coordinate"]
        pyautogui.moveTo(x, y, duration=0.2)
        return f"moved mouse to ({x}, {y})"

    elif action_type == "drag":
        sx, sy = action["startCoordinate"]
        ex, ey = action["endCoordinate"]
        pyautogui.drag(sx, sy, ex - sx, ey - sy, duration=0.3)
        return f"dragged from ({sx},{sy}) to ({ex},{ey})"

    elif action_type == "wait":
        duration = action.get("duration", 1000) / 1000  # ms → seconds
        await asyncio.sleep(duration)
        return f"waited {duration}s"

    else:
        return f"unknown action: {action_type}"

Phase 2 — Chrome Launcher with Persistent Profile
executor/chrome.py
Launches Chrome pointing at a persistent user-data-dir. Login state persists automatically.
pythonimport subprocess
import sys
import time
import httpx
from pathlib import Path

CHROME_BINARIES = {
    "win32":  [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ],
    "linux":  ["google-chrome", "google-chrome-stable", "chromium-browser"]
}

def find_chrome() -> str:
    platform = sys.platform
    candidates = CHROME_BINARIES.get(platform, [])
    for c in candidates:
        if Path(c).exists():
            return c
        # Try PATH lookup for linux
        import shutil
        found = shutil.which(c)
        if found:
            return found
    raise RuntimeError("Chrome not found. Install Chrome or set CHROME_PATH in .env")

def launch_chrome(profile_name: str = "default", port: int = 9222) -> subprocess.Popen:
    user_data_dir = Path.home() / ".computer-agent" / "profiles" / profile_name / "user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    chrome_path = find_chrome()
    
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]
    
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for Chrome to be ready
    _wait_for_chrome(port)
    return proc

def _wait_for_chrome(port: int, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=1)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Chrome did not start on port {port} within {timeout}s")

Phase 3 — User Communication
comms/user.py
Blocking ask and non-blocking update. In future this routes to Telegram.
pythonasync def ping_user(msg: str, type: str = "ask") -> str:
    if type == "update":
        print(f"\n[AGENT UPDATE] {msg}")
        return ""
    elif type == "ask":
        print(f"\n[AGENT NEEDS INPUT] {msg}")
        response = input("Your response: ").strip()
        return response

Phase 4 — System Prompt
core/prompts.py
pythonSYSTEM_PROMPT = """
You are a computer use agent controlling a real desktop via screenshots.

WORKFLOW:
1. You receive a screenshot of the current screen
2. You decide the next single action to take
3. Return exactly one action
4. You will receive a new screenshot after each action
5. Repeat until the task is complete

ACTIONS AVAILABLE:
- screenshot: request a fresh screenshot (use when screen may have changed)
- click: click at coordinates { coordinate: [x, y], button: "left"|"right"|"middle" }
- double_click: double-click at coordinates { coordinate: [x, y] }
- type: type text { text: "..." }
- key: press key or combo { key: "enter" | "ctrl+c" | "ctrl+v" | ... }
- scroll: scroll at position { coordinate: [x, y], direction: "up"|"down", amount: 3 }
- move_mouse: move without clicking { coordinate: [x, y] }
- wait: pause { duration: 1000 } (milliseconds)

SPECIAL SIGNALS (return as plain text, not as an action):
- DONE: <result> — task is complete, include what was accomplished
- NEED_INPUT: <question> — you need the user to do something (login, OTP, etc.)
- FAILED: <reason> — task cannot be completed

RULES:
- One action per response
- After clicking something that triggers navigation, always request a screenshot next
- For login pages: signal NEED_INPUT asking user to log in, then wait for confirmation
- For OTP fields: signal NEED_INPUT with the site name, fill the returned code
- For password fields: always use type action (never key)
- Never guess coordinates — only act on what you can see in the screenshot
- If the screen hasn't changed after an action, try a different approach
"""

Phase 5 — Main Agent Loop
core/agent.py
pythonimport google.generativeai as genai
import json
import re
from core.prompts import SYSTEM_PROMPT
from core.models import AgentResult
from executor.screenshot import take_screenshot
from executor.actions import execute_action
from comms.user import ping_user

class ComputerAgent:
    def __init__(self, model: str = "gemini-2.0-flash-exp"):
        self.model = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_PROMPT
        )
        self.max_turns = 50

    async def run(self, task: str) -> AgentResult:
        print(f"\n[ComputerAgent] Starting task: {task}")
        
        history = []
        
        for turn in range(self.max_turns):
            # Take screenshot
            screenshot_b64, screen_size = take_screenshot()
            
            # Build message: task context on turn 1, just screenshot after
            if turn == 0:
                user_content = [
                    {"text": f"Task: {task}\n\nCurrent screen:"},
                    {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}}
                ]
            else:
                user_content = [
                    {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}}
                ]
            
            history.append({"role": "user", "parts": user_content})
            
            # Call Gemini
            response = self.model.generate_content(history)
            reply = response.text.strip()
            
            history.append({"role": "model", "parts": [{"text": reply}]})
            
            print(f"\n[Turn {turn + 1}] Model: {reply[:200]}")
            
            # Parse response
            result = await self._handle_reply(reply)
            
            if result["type"] == "done":
                return AgentResult(status="done", deliverable=result["value"])
            
            elif result["type"] == "failed":
                return AgentResult(status="failed", reason=result["value"])
            
            elif result["type"] == "need_input":
                # Block and ask user
                user_response = await ping_user(result["value"], type="ask")
                # Inject user response as next message
                history.append({
                    "role": "user",
                    "parts": [{"text": f"User response: {user_response}"}]
                })
                continue  # Don't take screenshot this turn, let model process
            
            elif result["type"] == "action":
                action_result = await execute_action(result["value"])
                print(f"[Turn {turn + 1}] Executed: {action_result}")
                # Small pause for screen to settle
                import asyncio
                await asyncio.sleep(0.5)
                # Loop continues — next turn takes fresh screenshot
        
        return AgentResult(status="failed", reason="Max turns reached")

    async def _handle_reply(self, reply: str) -> dict:
        # Check for signal strings first
        if reply.startswith("DONE:"):
            return {"type": "done", "value": reply[5:].strip()}
        
        if reply.startswith("FAILED:"):
            return {"type": "failed", "value": reply[7:].strip()}
        
        if reply.startswith("NEED_INPUT:"):
            return {"type": "need_input", "value": reply[11:].strip()}
        
        # Try to parse as JSON action
        # Model may wrap in ```json``` or return raw JSON
        json_match = re.search(r'\{.*\}', reply, re.DOTALL)
        if json_match:
            try:
                action = json.loads(json_match.group())
                return {"type": "action", "value": action}
            except json.JSONDecodeError:
                pass
        
        # If nothing parsed, ask for screenshot (safe default)
        return {"type": "action", "value": {"action": "screenshot"}}

Phase 6 — Schemas
core/models.py
pythonfrom pydantic import BaseModel
from typing import Optional, Literal

class AgentResult(BaseModel):
    status: Literal["done", "failed"]
    deliverable: Optional[str] = None
    reason: Optional[str] = None

Phase 7 — Entry Points
main.py — for dev/testing:
pythonimport asyncio
from core.agent import ComputerAgent
from executor.chrome import launch_chrome

async def main():
    # Launch Chrome with persistent profile
    chrome = launch_chrome(profile_name="default")
    
    agent = ComputerAgent()
    result = await agent.run("Go to google.com and search for 'Gemini computer use'")
    
    print(f"\nResult: {result.status}")
    print(f"Deliverable: {result.deliverable or result.reason}")

if __name__ == "__main__":
    asyncio.run(main())
Parent agent calling interface — single function to expose:
python# This is what the parent agent calls
async def run_computer_task(
    task: str,
    profile: str = "default",
    launch_browser: bool = True
) -> dict:
    if launch_browser:
        launch_chrome(profile_name=profile)
    
    agent = ComputerAgent()
    result = await agent.run(task)
    return result.model_dump()
```

---

### Build Order
```
Phase 1 — executor/screenshot.py + executor/actions.py
          Test: take screenshot, execute a click, confirm mouse moved

Phase 2 — executor/chrome.py
          Test: launch Chrome, verify it opens with your profile logged in

Phase 3 — comms/user.py
          (trivial, 10 lines)

Phase 4 — core/prompts.py + core/models.py

Phase 5 — core/agent.py
          Test: run("open a new tab in Chrome")

Phase 6 — Wire run_computer_task() into parent agent
```

---

### The Login + OTP Flow in Practice
```
Parent: run_computer_task("post on LinkedIn: 'Hello world'")
    ↓
Agent navigates to linkedin.com
    ↓
Screenshot shows login page
    ↓
Gemini returns: NEED_INPUT: Please log in to LinkedIn. 
                Click confirm when done.
    ↓
ping_user blocks → you log in manually → type "done"
    ↓
Agent continues with logged-in session
    ↓
Future runs: LinkedIn already logged in, agent proceeds directly
    ↓
OTP case: Gemini returns NEED_INPUT: LinkedIn sent an OTP. 
          Please send me the code.
    ↓
You reply "482910" → agent fills the field