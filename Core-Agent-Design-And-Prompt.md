The Agent Prompt Protocol — Start to Finish
The Core Truth First

Tools:   FROZEN at session start. Never change mid-conversation.
Skills:  ALL eligible ones listed in system prompt. Model picks at runtime.
Context: Grows turn by turn → gets compacted when window fills.
There is no dynamic tool loading. No skill relevance scoring on the server. The protocol lives entirely in the prompt — the model is the runtime.

The System Prompt — Exact Structure
When a session starts, a single system prompt is assembled once. This is what the model sees before it ever receives the first user message.


┌─────────────────────────────────────────────────────────────┐
│  SYSTEM PROMPT (built once, frozen for session lifetime)    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1.  Identity                                               │
│      "You are a personal assistant running inside OpenClaw" │
│                                                             │
│  2.  Tooling                                                │
│      "Tool availability (filtered by policy):"              │
│       exec, read, write, edit, browser, web_search...       │
│      + how to use tool calls, context overflow advice       │
│                                                             │
│  3.  Tool Call Style                                        │
│      narration guidelines, when to comment on tool use      │
│                                                             │
│  4.  Safety                                                 │
│      self-preservation rules, safeguard compliance          │
│                                                             │
│  5.  CLI Quick Reference                                    │
│      openclaw gateway commands, self-management             │
│                                                             │
│  6.  Skills  ← THE SELECTION PROTOCOL                       │
│      <available_skills>                                     │
│        - github: GitHub operations via gh CLI               │
│        - notion: Notion pages and databases                 │
│        - coding-agent: Delegate to Claude Code or Codex     │
│        - tmux: Session and window management                │
│        ... (only eligible ones based on PATH binaries)      │
│      </available_skills>                                    │
│      "Scan descriptions. If one clearly applies: read its   │
│       SKILL.md then follow it. Otherwise: ignore."          │
│                                                             │
│  7.  Memory Recall                                          │
│      "Search memory before answering about prior work"      │
│                                                             │
│  8.  Model Aliases (if configured)                          │
│  9.  Workspace path + notes                                 │
│  10. Documentation links                                    │
│  11. Sandbox info (if sandboxed)                            │
│  12. Authorized senders / owner IDs                         │
│  13. Current date & time + timezone                         │
│                                                             │
│  14. Bootstrap Files  ← AGENTS.md + workspace context       │
│      "The following project context files have been loaded:"│
│      [AGENTS.md full content]                               │
│      [SOUL.md full content if present]                      │
│      [USER.md full content if present]                      │
│      [MEMORY.md full content if present]                    │
│                                                             │
│  15. Messaging protocol (how to route replies)              │
│  16. Silent replies protocol                                │
│  17. Heartbeat protocol                                     │
│                                                             │
│  18. Runtime metadata                                       │
│      agentId, OS, arch, Node version, model name, shell,    │
│      channel, capabilities, workspace root                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
Minimal mode (subagents, cron): sections 7, 15, 16, 17 are stripped. Leaner prompt.

The Bootstrap Files — What AGENTS.md Actually Is
The "bootstrap context" is not just AGENTS.md. It's a set of files loaded from the workspace and injected verbatim:


Workspace root
  ├─ AGENTS.md      ← primary agent instructions (main prompt engineering lever)
  ├─ SOUL.md        ← persona, tone ("be terse", "use emojis", "formal voice")
  ├─ IDENTITY.md    ← role definition
  ├─ USER.md        ← user preferences and facts
  ├─ TOOLS.md       ← guidance for external tools specific to this workspace
  ├─ HEARTBEAT.md   ← polling/alerting logic
  └─ MEMORY.md      ← persistent memory from prior sessions
All of these get injected into the system prompt, in that order, under "Project Context." They're the workspace-level personality layer.

Budget: Per-file max ~32KB. Total max ~192KB. Anything over gets truncated with a warning injected before the content.

Subagents get a restricted list: Only AGENTS.md, SOUL.md, IDENTITY.md, USER.md, TOOLS.md. No HEARTBEAT or MEMORY — they don't need that.

The Skill Selection Protocol — How It Actually Works
This is the key insight. There is no server-side relevance engine.

Step 1 — Eligibility filter (server-side, binary)
Before the model sees anything, the server filters the ~45 bundled skills:


For each skill:
  ├─ Is it in the config deny list? → exclude
  ├─ Is there a bundled allowlist AND this skill isn't in it? → exclude
  ├─ Does it require OS=mac but we're on Linux? → exclude
  ├─ Does it require binary "gh" but `which gh` fails? → exclude
  ├─ Does it require env var GH_TOKEN but it's not set? → exclude
  └─ Passes all checks? → include in prompt
No fuzzy matching. No scoring. Pure boolean per requirement.

The result might be 8 skills on a minimal machine with only git and node, or 30+ on a fully tooled workstation.

Step 2 — Listed in system prompt (all eligible ones)
The surviving skills are injected as a flat list:


<available_skills>
  - coding-agent: Delegate coding tasks to Claude Code, Codex, or Pi agents
  - github: GitHub operations via gh CLI: PRs, issues, workflows
  - tmux: Tmux session and window management
  - weather: Get current weather and forecasts
  - notion: Notion pages, databases, and blocks
</available_skills>

Before replying: scan <available_skills> descriptions.
  - If exactly one skill clearly applies: read its SKILL.md via `read`, then follow it.
  - If multiple could apply: choose the most specific one, read and follow it.
  - If none clearly apply: do not read any SKILL.md.
Step 3 — Model heuristic (runtime, the model decides)
The model reads those descriptions and makes the call:


User: "create a PR for this branch"

Model thinks:
  → "github" skill says "GitHub operations via gh CLI: PRs" → that's it
  → call read(path: "~/.openclaw/skills/github/SKILL.md")
  → reads the skill content (gh pr create commands, flags, examples)
  → now executes: exec("gh pr create --title '...' --body '...'")

User: "refactor the auth module"

Model thinks:
  → "coding-agent" says "delegate coding tasks" → but I can also just do it
  → "github" says "PRs, issues" → not relevant
  → none clearly apply → skip all skills
  → just calls read/edit/write directly
The model is the router. The skill file is fetched on-demand via read.

This means a skill's full content (examples, flags, edge cases, exact commands) only enters the context when the model explicitly decides to read it. The descriptions in the prompt are just ~10 word teasers.

What Happens Turn by Turn

SESSION START
  │
  ├─ System prompt assembled (once, frozen)
  │    tools list, skill teasers, AGENTS.md, workspace context
  │
  ▼
TURN 1 — User message arrives
  │
  │  Full context sent to LLM:
  │  [system prompt] + [user: "create a PR"]
  │
  ├─ LLM decides: skill "github" applies
  ├─ Calls: read(SKILL.md)            ← tool call 1
  │    → SKILL.md content added to context
  ├─ Calls: exec("git branch --show-current") ← tool call 2
  │    → branch name returned
  ├─ Calls: exec("gh pr create ...")  ← tool call 3
  │    → PR URL returned
  └─ Replies: "PR created: https://github.com/..."
  │
  ▼
TURN 2 — User message arrives
  │
  │  Full context sent to LLM:
  │  [system prompt]
  │  + [user: "create a PR"] 
  │  + [assistant: tool calls + "PR created..."]
  │  + [user: "now add a changelog entry"]
  │
  ├─ No skill clearly applies → skip skill read
  ├─ Calls: read("CHANGELOG.md")
  ├─ Calls: edit("CHANGELOG.md", ...)
  └─ Replies: "Added changelog entry"
  │
  ▼
TURN N — Context window filling up
  │
  ├─ context-window-guard checks token count
  │    < 32,000 tokens remaining → warn in logs
  │    < 16,000 tokens remaining → trigger compaction
  │
  ├─ COMPACTION runs:
  │    Take oldest 40% of message history
  │    Summarize via LLM call:
  │      "User asked to create PR → skill read → exec gh → replied with URL
  │       Then added changelog entry → edit CHANGELOG.md"
  │    Replace those messages with the summary
  │    Conversation continues with summary + recent messages
  │
  └─ Tools list unchanged. Skill teasers unchanged. Only history compressed.
Context Window Management — The Numbers

Model context window: e.g. 200,000 tokens (Claude Sonnet)
  │
  ├─ System prompt:         ~2,000–8,000 tokens (varies with bootstrap files)
  ├─ Skills list:           ~500–2,000 tokens (descriptions only)
  ├─ AGENTS.md injection:   ~500–8,000 tokens (depends on file size, 32KB max)
  ├─ Available for history: everything else
  │
  ├─ Each tool result:      capped at 30% of remaining window
  │                         (a big file read can eat 60,000 tokens)
  ├─ Hard truncation at:    400,000 chars absolute
  │
  ├─ Warn threshold:        32,000 tokens remaining
  ├─ Hard stop / compact:   16,000 tokens remaining
  │
  └─ Compaction chunks:
       Summarize oldest 40% of messages
       Keep 60% most recent intact
       20% safety buffer on token estimates
Tool results are the biggest variable. A read of a large file can consume a huge chunk. That's why the 30% cap exists — one tool call can't swallow the entire window.

Are Tools Dynamic? Is There a Protocol?
Short answer: No dynamic loading. Yes, it is a protocol — but the protocol is the prompt itself.

Tools — truly frozen

Build once at session start
  ↓
Tool list in system prompt: "You have: exec, read, write, edit, browser..."
  ↓
Same list for turn 1, turn 50, turn 100
  ↓
EVEN after compaction — the system prompt is NOT regenerated
  ↓
If a tool is unavailable (policy change, binary gone), session must restart
The model cannot "request" a new tool. The human has to reconfigure and restart.

Skills — pseudo-dynamic (model-driven lazy loading)

Session start: model sees 8 skill teasers (descriptions only)
               NO skill content in context yet

Turn 1: model reads github/SKILL.md → content enters context
         now model knows exact gh flags and commands

Turn 3: model reads coding-agent/SKILL.md → more content enters
         context growing with each skill read

Compaction: skill content can get summarized away
            next time that skill is needed, model reads it again
Skills are lazy-loaded on demand by the model. They're not pre-fetched. The model asks for a skill file like it would ask for any other file — via the read tool.

The actual "protocol" is the instruction chain

System prompt instructs the model:
  1. "Here are your tools: exec, read, write..."
  2. "Here are available skills (descriptions): github, notion, tmux..."
  3. "If a skill clearly applies → read its SKILL.md first, then follow it"
  4. "Search memory before answering about past work"
  5. "For coding tasks: consider using sessions_spawn to delegate"
  6. "Reply to user messages in the current channel"
  7. "For background tasks: exec with background=true, poll with process"
The model interprets this protocol on every single turn. There's no middleware enforcing "you must read the skill file first." The model follows the instructions because they're in the prompt. If the model decides to skip the skill read, it will.

The Full Lifecycle in One Diagram

BEFORE SESSION
══════════════
Disk scan:
  which gh? → ✓ found     → github skill eligible
  which notion? → ✗ absent → notion skill excluded
  $GH_TOKEN set? → ✓       → github confirmed

SESSION START
═════════════
Assemble system prompt:
  [identity + tools + skill teasers + AGENTS.md + workspace]
  ← this is the "base prompt", built once, never rebuilt

TURN 1 — first user message
═════════════════════════════
LLM receives: [system prompt] + [user message]
LLM responds with tool calls:
  ┌─ read skill? → yes → read(SKILL.md) → content in context
  ├─ run commands → exec/read/write/edit
  └─ reply text

TURN 2-N — growing conversation
═════════════════════════════════
LLM receives: [system prompt] + [all history] + [new user message]
History grows each turn:
  [user msg 1] [assistant + tool calls 1]
  [user msg 2] [assistant + tool calls 2]
  ...

CONTEXT FILLS UP
═════════════════
token count > 200k - 16k (hard floor)
  → compaction:
      oldest 40% messages → summarized by LLM call
      summary replaces those messages
      conversation continues, context shrunk

TOOLS: same throughout
SKILLS: re-read if compaction evicted previous skill read
SYSTEM PROMPT: unchanged throughout, even after compaction
The One-Sentence Model
The system prompt is a protocol document the model reads and executes autonomously — tools are its API surface (fixed), skills are optional reference docs it fetches on demand, and context compaction is the garbage collector that keeps the conversation alive indefinitely.