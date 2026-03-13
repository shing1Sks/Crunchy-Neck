# Crunchy Neck

A minimal Python AI agent with a "do anything" spirit.

---

## Origin

I first came across [OpenClaw](https://github.com/openclaw/openclaw) (moltbot / clawedbot / OpenClaw) and my first reaction was: *how the hell does this work?*

So I started building. A couple of iterations — complete failures, one or two small wins. Then I actually sat down and analyzed OpenClaw's structure, took what I learned, and designed something from scratch in Python.

I wasn't chasing feature parity. The goal was a small, sharp core that covers ~80–85% of what something like OpenClaw can do — without dragging in the complexity. Define the crucial capabilities, let the model handle the rest.

Still a work in progress. Already shocked by what it can do.

---

## What It Is

Crunchy Neck is a personal AI agent. Not an assistant — a companion. It treats your work like its own, thinks ahead, and gets things done.

- Powered by **OpenAI** (GPT-5.2, `reasoning_effort=low`)
- Talks to you via **Terminal** or **Telegram**
- Acts through a set of 13 tools covering most things you'd want an agent to do
- Includes **Scout** — a computer-use subagent for browser and desktop GUI automation

If you're new to agents and want something simple to fork, modify, and make your own — this is designed for that.

---

## Tools

| Tool | What it does |
|---|---|
| `exec` | Run shell commands |
| `process` | Manage background jobs |
| `read` / `write` / `edit` | File operations |
| `browse` | Delegate to Scout (browser or desktop automation) |
| `remember` | Semantic long-term memory via ChromaDB |
| `ping_user` | Send updates, ask questions, prompt for input |
| `send_user_media` | Deliver files, audio, video |
| `snapshot` | Take screenshots |
| `tts` | Text-to-speech via Inworld |
| `image_gen` | Generate images via Gemini |
| `web_search` | Built-in OpenAI web search |

### Scout

Scout is a full computer-use subagent. Give it a browser task or a desktop task — it handles the rest. Uses Chrome with your existing profiles (logins stay active), and can interact with any Windows app. Can ask you for OTPs or confirmations mid-task.

---

## Setup

**Prerequisites:** Python 3.10+, OpenAI API key (with GPT-5.2 access)

```bash
git clone https://github.com/your-username/crunchy-neck-agent
cd crunchy-neck-agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Fill in your API keys in .env
```

Set your `PYTHONPATH` to the project root before running:

```bash
# Windows (PowerShell)
$env:PYTHONPATH = "C:\path\to\crunchy-neck-agent"

# Linux / macOS
export PYTHONPATH="/path/to/crunchy-neck-agent"
```

**API Keys:**

| Key | Purpose | Required? |
|---|---|---|
| `OPENAI_API_KEY` | Main agent, compaction, session wrapup | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram medium | Only for `--medium telegram` |
| `TELEGRAM_CHAT_ID` | Telegram medium | Only for `--medium telegram` |
| `INWORLD_API_KEY` | TTS tool | Optional |
| `GEMINI_API_KEY` | Image generation tool | Optional |

---

## Running

```bash
# Terminal (default)
python crunchy-neck-agent.py

# Terminal with a specific workspace
python crunchy-neck-agent.py --workspace /path/to/workspace

# Telegram
python crunchy-neck-agent.py --medium telegram --workspace /path/to/workspace
```

---

## Project Structure

```
crunchy-neck-agent.py   # Entry point
requirements.txt
.env.example

agent_utils/            # System prompt builder, tool schemas, dispatcher
agent_design/           # Session wrapup, compaction, skills, identity
comm_channels/          # Terminal and Telegram adapters
computer_agent/         # Scout subagent (browser + desktop automation)
tools/                  # 12 custom tools
skills/                 # Skill library (scout, coding_agent, gog)
memory/                 # Long-term memory (ChromaDB) + session history

PERSONALITY.md          # Agent character — injected into system prompt
USER.md                 # User profile — injected into system prompt
MEMORY.md               # Auto-written session log
```

---

## What's Next

This is a living project. A few things on the list:

- Agent Scheduling (next)
- Web interface with richer controls
- Live / streaming feel from the agent
- WhatsApp Desktop skill for Scout
- Scout building its own skills from actions it's performed
- Suggestions surface (agent proactively flags things)

Updates land whenever there's time.

---

## Inspiration

Built after studying the structure of **OpenClaw** (moltbot / clawedbot). Credit to that project for the mental model — this is an independent reimplementation, not a fork.

---

> *"Not an assistant. A companion."*
