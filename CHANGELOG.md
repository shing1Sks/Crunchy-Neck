# Changelog

All notable changes to Crunchy-Neck-Agent are documented here.

---

## [Unreleased] — 2026-03-15 (patch 1)

### Added — Scout `snapshot` function tool (`computer_agent/agent.py`, `computer_agent/prompts.py`)

Scout now has a dedicated `snapshot` function tool that saves screenshots directly to `.agent/snapshots/` without relying on OS-level shortcuts (Win+Shift+S, etc.).

- New `snapshot_tool_fn` function-call definition registered alongside the existing `computer` CUA tool.
- Scout's loop handles `function_call` items where `name == "snapshot"`, calling `snapshot_command` and returning the saved path as tool output.
- System prompt (`_SHARED_TOOLS` section) instructs the model to always use `snapshot()` instead of OS screenshot methods; documents `filename`, `x1/y1/x2/y2`, and `monitor` parameters.
- `_SHARED_TOOLS` injected into both `BROWSER_SYSTEM_PROMPT` and `DESKTOP_SYSTEM_PROMPT`.

### Changed — Snapshot tool: `region` array replaced with `x1/y1/x2/y2` coordinates (`tools/snapshot/`)

The snapshot tool's crop parameter was redesigned from a `[x, y, width, height]` array to four explicit integer fields for better ergonomics with LLM function calling.

- `SnapshotParams`: removed `region: list[int] | None`; added `x1`, `y1`, `x2`, `y2` (all `int | None`) and `filename: str | None`.
- `snapshot_command`: bounding box built from `x1/y1/x2/y2` when all four are provided; filename derived from `params.filename` (stem preserved, extension forced to match format), falling back to timestamp name.
- `TOOL_DEFINITION` (`tools/snapshot/__init__.py`): updated schema — replaced `region` array with four individual integer properties; added `filename` string property with description.

### Added — Image file support in the read tool (`tools/read/`)

The `read` tool can now return image files to the model as vision content blocks instead of erroring or returning garbage bytes.

- New `ReadResultImage` datatype (`read_types.py`): status `"image"`, carries `mime_type`, `b64_data`, and `size_bytes`.
- `read_command` (`read_tool.py`): fast-path on extension (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`) reads bytes and returns `ReadResultImage` with base64-encoded data; never hits binary-detection logic.
- PDF fast-path also added: uses `pypdf` to extract text page-by-page; returns `ReadResultDone` with structured page content; gracefully returns an error if `pypdf` is not installed.

### Added — Image dispatch pipeline (`agent_utils/tool_dispatcher.py`, `crunchy-neck-agent.py`)

The OpenAI Chat Completions API cannot render images inside `role:tool` messages. A new dispatch pipeline routes image results through a separate `role:user` message.

- New `ImageDispatchResult` dataclass (`tool_dispatcher.py`): carries `tool_text` (plain string for the tool result slot) and `image_block` (OpenAI `image_url` content block).
- `dispatch()` return type widened to `str | ImageDispatchResult`; returns `ImageDispatchResult` when the tool result is `ReadResultImage`.
- `_run_agent_turn` (`crunchy-neck-agent.py`): collects `ImageDispatchResult` instances into `pending_image_blocks` per batch; after all tool-call results are appended, injects a single `role:user` message containing all image blocks so the model can see the images on the next turn.

---

## [Unreleased] — 2026-03-14 (patch 1)

### Fixed — Scout `pending_safety_checks` API 400 error (`computer_agent/agent.py`)

OpenAI's Responses API sometimes includes `pending_safety_checks` in a `computer_call` response item. The loop was echoing the full item back via `_to_dict(item)`, which kept `pending_safety_checks` in the next request's `input` — a field the API rejects with HTTP 400.

- Fix: pop `pending_safety_checks` from the echoed `call_dict` before appending to `input_list`.
- Fix: carry the popped checks forward as `acknowledged_safety_checks` on the `computer_call_output` item, which is the correct acknowledgement mechanism per OpenAI's CUA spec.

---

## [Unreleased] — 2026-03-13 (patch 1)

### Fixed — Telegram communication flow: duplicate messages, "Listening..." accumulation, stale update bubble

Three compounding UX bugs fixed across `sender.py`, `ping_tool.py`, and `crunchy-neck-agent.py`.

**Bug 1 — Duplicate final message** (`crunchy-neck-agent.py`):
`_send_thinking_snippet` showed the model's final response text in the update bubble, then `_send_final_response` sent the same text as a chat message. The previous `_clear_update_anchor` fix removed `last_update_message_id` from state before `_delete_status_message` could run, leaving the bubble and creating a visible duplicate.
- Fix: call `_delete_status_message` inside `_run_agent_turn` **before** `_send_final_response`, so the bubble is gone before the chat message appears.

**Bug 2 — "Listening..." accumulates / bad position** (`comm_channels/telegram/sender.py`):
After the user replied, `send_query_msg` never deleted the "Listening..." message. It sat in the timeline forever; next session it was edited in-place from the old (scrolled-up) position.
- Fix: after `_poll_for_text_reply` returns a successful response, call `delete_message` on `sent_msg_id` and clear `listen_message_id` from state. Every session now gets a fresh "Listening..." at the bottom.

**Bug 3 — Update bubble stays above mid-session queries** (`tools/ping/ping_tool.py`):
When the model called `query:msg` or `query:options`, `_clear_update_anchor` only removed the state key — it never deleted the Telegram message. The stale progress bubble stayed above the query, and subsequent updates edited it above where the user was looking.
- Fix: replaced `_clear_update_anchor` with `_delete_and_clear_anchor(workspace_root, cfg)` — calls `delete_message` on the anchor first, then clears state. Called **before** sending `query:msg` or `query:options` so the query appears on a clean timeline.
- Removed `_clear_update_anchor` entirely from the `chat` branch (main loop now handles deletion before that point).

**Resulting clean flow per session:**
```
[Bot] Listening...                ← NEW message every session
[User] reply → Listening... deleted immediately
[Bot] Working on it...            ← new anchor; all tool updates edit this
      [mid-session query:]
← anchor DELETED before query
[Bot] Please log in to X          ← appears on clean line
[User] done
[Bot] Working on it...            ← NEW anchor below user reply
← anchor DELETED
[Bot] Here's the result!          ← single clean chat message
[Bot] Listening...                ← fresh at bottom
```

---

## [Unreleased] — 2026-03-13

### Added — `tools/browse/` — Scout computer-use subagent tool (`tools/browse/`)

Crunchy can now delegate browser and desktop GUI tasks to Scout via the `browse` tool.

- `browse_types.py` — `BrowseParams` (task, mode, launch_browser, max_turns), `BrowseResultDone`, `BrowseResultFailed`
- `browse_tool.py` — `browse_command()` reads `OPENAI_API_KEY` from env/.env, builds `RunConfig`, calls `computer_agent.agent.run()`, returns typed result
- `__init__.py` — `TOOL_DEFINITION` with full OpenAI function-calling schema
- `test_browse.py` — 5 unit tests (defaults, custom params, no-key failure, result fields)
- Wired into `tools/__init__.py`, `agent_utils/tool_schemas.py`, `agent_utils/tool_dispatcher.py` (passes `medium` through), `agent_utils/system_prompt.py`

---

### Added — `skills/scout/SKILL.md` — Scout usage skill for Crunchy

Teaches Crunchy when and how to use the `browse` tool:

- When to use (JS-rendered scraping, form filling, desktop automation, login-required sites)
- When not to use (anything exec/read/write handles directly)
- Full parameter table, quick examples for browser and desktop mode
- Login retry pattern: if Scout returns failed with login reason, ask user to log in then retry with `launch_browser=False`
- Progress update guidance (send one ping before long tasks; Scout sends its own live action updates)

---

### Added — `computer_agent/scout_log.py` — structured per-session JSONL logger

Every Scout run now writes a full turn-by-turn log to `.agent/scout/logs/YYYYMMDD_<session_id>.jsonl`. Log path is sent as the first ping update.

Events logged: `session.start`, `session.end`, `turn.start`, `model.response`, `action.execute`, `action.result`, `action.error`, `screenshot.taken`, `signal.detected`, `text.output`, `implicit_done`, `no_progress`, `need_input.sent/reply/timeout`, `compaction.skipped/done/error`, `api.error`, `chrome.launch`, `chrome.launch_error`

---

### Changed — `computer_agent/agent.py` — full logging instrumentation + implicit-DONE fix

- Imports and uses `ScoutLog` throughout the turn loop
- `compaction.skipped/done/error` events replace bare `print()` calls
- Each action execution now wrapped in `try/except` — `action.error` logged, loop continues instead of crashing
- **Bug fix:** when model returns text without `DONE:` prefix and takes no action, treated as `AgentResultDone(deliverable=last_text)` instead of `AgentResultFailed` ("no progress")

---

### Fixed — `computer_agent/actions.py` — non-ASCII text corruption via clipboard fallback

`pyautogui.write()` silently drops or corrupts non-ASCII characters (em dashes `—`, curly quotes `""`, accented characters). Scout would stop with `FAILED` when asked to type such text.

- Pure ASCII text: still uses `pyautogui.write()` (reliable, character-by-character)
- Any non-ASCII text: copies to clipboard with `pyperclip.copy()` then pastes with `Ctrl+V` — preserves exact string
- Transparent to the model — no prompt changes needed
- Added `pyperclip` to `requirements.txt`

---

## [Unreleased] — 2026-03-12 (patch 2)

### Fixed — `image_gen` image extraction and save (`tools/image_gen/image_gen_tool.py`)

`part.as_image()` was incompatible with some `google-genai` SDK versions and raised `Image.save() got an unexpected keyword argument 'format'`. Replaced with direct raw-bytes extraction.

- Read `part.inline_data.data` directly; base64-decode if the SDK returns a string
- Save via `out_path.write_bytes(raw_bytes)` — no PIL involved in the write path
- PIL now used only for dimension reading (`width`, `height`), wrapped in a non-fatal `try/except` so missing Pillow doesn't break saves

---

### Changed — `send_query_msg` reuses existing "Listening..." prompt (`comm_channels/telegram/sender.py`, `ping_tool.py`)

Previously sent a new `ForceReply` message every time the agent waited for user input, cluttering the chat. Now:

- Saves the sent message ID to state as `listen_message_id`
- On next call, attempts `editMessageText` in-place; only sends a fresh message if the edit fails
- `_poll_for_text_reply` relaxed: accepts **any** text message with a higher ID than the prompt (no longer requires an explicit reply-to), making it work without ForceReply threading
- `send_query_msg` now receives `workspace_root` to read/write state — signature updated in both `comm_channels/ping_tool.py` and `tools/ping/ping_tool.py`

---

### Added — final-response delivery + status-message cleanup (`crunchy-neck-agent.py`)

After the agent loop completes and before wrapup:

- `_send_final_response(content)` — sends the agent's final answer as a persistent `chat` message on Telegram (previously only printed to terminal)
- `_delete_status_message()` — deletes the ephemeral "Working on it..." `update` message from Telegram once the final answer is visible; updates state to clear `last_update_message_id`

---

### Fixed — `send_update` state persistence bug (`comm_channels/telegram/sender.py`)

`save_state` was called with `{"last_update_message_id": new_id}` — a new dict — discarding all other state keys (e.g. `listen_message_id`). Fixed by mutating the loaded state dict and saving the whole thing.

---

### Changed — `_poll_for_callback` confirms chosen option (`comm_channels/telegram/sender.py`)

After the user taps an inline button:

- Edits the original message to append `✅ *chosen_option*` in MarkdownV2
- Passes `reply_markup={"inline_keyboard": []}` to remove the buttons from the message

---

### Added — `reply_markup` param + `delete_message` to Telegram client (`comm_channels/telegram/client.py`)

- `edit_message_text` now accepts an optional `reply_markup` dict — pass `{"inline_keyboard": []}` to strip buttons
- New `delete_message(token, chat_id, message_id)` — deletes a message; returns `False` silently if already gone (idempotent); imported in `sender.py`

---

### Changed — `skill_use.py` skips binary availability check (`agent_design/skill_use.py`)

Removed the `anyBins` PATH check from `_is_eligible`. All skills are now included in the system prompt regardless of whether their required binary is on PATH. `import shutil` removed.

---

### Changed — `exec` + `process` tool descriptions improved for stdin guidance (`tools/exec/__init__.py`, `tools/process/__init__.py`, `tools/process/process_tool.py`)

Addresses repeated agent confusion around `--body-file -` hanging processes:

- `exec` description: added "Never use `--body-file -` or any stdin-until-EOF pattern; pass content via the `stdin` parameter instead"
- `exec.stdin` description: clarified it is the preferred alternative to piped stdin
- `process.action` description: added per-action explanations; `close-stdin` noted as the EOF-unblock escape hatch
- `process.keys` description: added multi-line guidance; recommends `exec.stdin` at launch over send-keys loops
- `process_tool.py` poll hint: if a process has been running >3 s with zero output lines, emits a hint identifying the likely stdin-block and telling the agent to kill + re-run with `stdin=`

---

## [Unreleased] — 2026-03-12

### Added — `crunchy-neck-agent.py` + `agent_utils/` (main agent loop)

The full agent is now wired together and runnable.

**Entry point:** `python crunchy-neck-agent.py [--medium terminal|telegram] [--workspace /path]`

**Session model:** each session = one user message in → tool-call loop → final reply → wrapup. Message history persists across sessions for the process lifetime.

**`agent_utils/` package (new):**

- `openai_helpers.py` — `make_client(api_key)` + `chat_complete(client, *, messages, tools, model)`. Single call-site that enforces `reasoning_effort="low"` on every OpenAI request.
- `tool_schemas.py` — wraps all 11 `TOOL_DEFINITION` dicts from `tools/__init__.py` in the OpenAI function-calling envelope `{"type":"function","function":...}`. No schema duplication — canonical source remains each tool's `__init__.py`.
- `tool_dispatcher.py` — `dispatch(tool_name, arguments_json, *, workspace_root, agent_session_id, medium) → str`. 11-branch dispatch table; filters args to valid dataclass fields; injects session `medium` into `ping_user` / `send_user_media` calls when model omits it; returns JSON string on success or `{"error":"..."}` on any exception.
- `system_prompt.py` — `build_system_prompt(*, workspace_root, medium, model)`. Assembles the frozen system prompt from: `build_identity_section()` (sections 1+7+14), inline tooling/style/safety/CLI sections, `build_skill_section()` (section 6), runtime metadata (model/date/OS/medium), messaging protocol, and `PERSONALITY.md` verbatim.

**Main loop (`crunchy-neck-agent.py`):**
- Outer loop: `_await_user_message()` → session → wrapup → repeat
- `_await_user_message`: terminal uses `input()`; Telegram long-polls via `ping_command(type="query:msg", timeout=3600)`, looping on timeout
- `_run_agent_turn`: compact → OpenAI call → dispatch tool calls → repeat; max 40 rounds; API errors appended as sentinel messages, never fatal
- Wrapup only fires when at least one tool was called — pure chat turns are skipped

**Live update pipeline (no AI, string-only):**
Every tool call produces two update pings, and any model thinking text produces one:
1. **Before tool**: `[tool_name] {args[:120]}` → `ping_user(type="update", title="tool")`
2. **After tool**: `[tool_name] → {first 3 lines of result}` → `ping_user(type="update", title="result")`
3. **Model thinking text**: first 2-3 non-empty lines → `ping_user(type="update", title="thinking")`

All updates use `edit_last_update=True` (in-place on Telegram), wrapped in `try/except`.

---

### Changed — `agent_design/memory_compaction.py` + `agent_design/session_wrapup_log.py`

- `max_tokens` → `max_completion_tokens` (gpt-5.2 rejects the old param name)
- `reasoning_effort="low"` added to both OpenAI calls
- `_extract_text()` now handles `None` content (assistant messages with only tool calls have `content=None`; previous code raised `TypeError: 'NoneType' object is not iterable`)

---

### Changed — `agent-design/` → `agent_design/` (directory rename)

Renamed to remove the hyphen so the package is importable as `agent_design` without `importlib` workarounds.

---

### Added — `OPENAI_API_KEY` to `.env.example`

Documented as required; used by the main agent model, compaction, and session wrapup. All three calls use `gpt-5.2` with `reasoning_effort="low"`.

---

### Added — `skills/coding_agent/SKILL.md` + `skills/gog/SKILL.md`

Two skills adapted from OpenClaw for Crunchy-Neck-Agent.

**`coding_agent`** — rewrote from OpenClaw format:
- Stripped to **Codex only** (removed Claude Code, Pi, OpenCode sections)
- Frontmatter updated to our format: `metadata.requires.anyBins: ["codex"]`
- Tool syntax adapted: `bash pty:true workdir:X command:...` → `exec(command=..., cwd=X, intent=..., background=True)`; `pty` dropped (not in our exec tool; `codex exec` is non-interactive)
- `openclaw system event` completion notifications → `ping_user(type="update")`
- All OpenClaw-specific path warnings removed
- Core patterns kept: `codex exec` one-shots, `--full-auto`/`--yolo` flags, git-init scratch trick, PR review (clone/worktree), parallel worktree batch fixing, process monitoring

**`gog`** — frontmatter only:
- `metadata.openclaw.requires.bins: ["gog"]` → `metadata.requires.anyBins: ["gog"]` (our eligibility format)
- Removed `homepage` field and openclaw install instructions
- Body (all `gog` CLI commands) unchanged

Both skills are now correctly picked up by `skill_use.py` eligibility filtering — appear in the system prompt only when the respective binary is on PATH.

---

## [Unreleased] — 2026-03-11

### Added — `agent-design/identity.py` + `agent-design/session_wrapup_log.py` + `PERSONALITY.md` (agent identity, memory lifecycle, personality)

Three modules completing the system-prompt foundation for the Crunchy agent.

---

#### `agent-design/identity.py`

Produces Sections 1 + 7 + 14 of the system prompt in a single call.

**Public API:**
- `build_identity_section(workspace_root, *, agent_name="Crunchy")` → `str` — main entry point; returns the complete identity + memory rules + bootstrap files block
- `load_user_md(workspace_root)` → `str` — reads `USER.md` in full (32 KB cap); returns `""` if absent
- `load_memory_md_extract(workspace_root, *, max_sessions=8)` → `str` — capped extract from `MEMORY.md`: Ongoing Threads always in full + last N `### Session:` blocks; returns `""` if absent

**What gets injected:**
- `## Identity` — "You are Crunchy, a personal autonomous agent…"
- `## Memory Rules` — when to update USER.md, when NOT to write MEMORY.md, ALWAYS use `remember()`
- `## User Profile` — full USER.md content (or placeholder prompting agent to create it)
- `## Recent Session Context` — MEMORY.md capped extract (or placeholder if missing)

**Template files:** `agent-design/templates/USER.md`, `agent-design/templates/MEMORY.md`

**Test suite:** `agent-design/tests/test_identity.py` — 29/29 checks passing

---

#### `agent-design/session_wrapup_log.py`

End-of-session hook. One LLM call → structured session log entry → written to `MEMORY.md`.

**Public API:**
- `run_session_wrapup_log(messages, *, api_key, workspace_root, today, config)` → `SessionWrapupResult`

**Flow:** serialise history → OpenAI call → parse `### Session:` entry + thread updates (`[ADD]`/`[KEEP]`/`[DONE]`) → prepend entry to `## Session Log` → merge thread updates into `## Ongoing Threads` → atomic write

**Result types:** `SessionWrapupResultDone` (`session_entry`, `threads_updated`, `memory_md_path`) / `SessionWrapupResultError` (`error_code`, `error_message`)

**Error codes:** `EMPTY_HISTORY`, `DEPENDENCY_MISSING`, `API_ERROR`, `WRITE_FAILED`, `INTERNAL`

**Config (`SessionWrapupConfig`):** `model`, `max_tokens`, `max_sessions_in_file` (default 60; overflow auto-compacted into `## Long-term History`)

**Test suite:** `agent-design/tests/test_session_wrapup_log.py` — 39/39 checks passing

---

#### `PERSONALITY.md`

Plain markdown file at the workspace root — just who Crunchy is. No code, no logic. Read and injected into the system prompt at session start alongside the other bootstrap files (USER.md, MEMORY.md).

Character: proactive, joyful, loyal, compassionate, creative, engineering-minded. Tone: casual and direct, "we" framing, enthusiastic when earned, never performs helpfulness.

---

### Added — `agent-design/skill_use.py` + `skills/_template/SKILL.md` (skill discovery & prompt injection)

Implements the skill selection protocol described in `Model-Skills-Architecture.md`. Produces Section 6 ("Skills") of the system prompt and is the only module the system-prompt builder needs to call.

**Core file:** `agent-design/skill_use.py`

**Public API:**
- `build_skill_section(workspace_root)` → `str` — main entry point; scans eligible skills and returns the complete Section 6 string (mandatory header + `<available_skills>` XML block) ready to insert into the system prompt
- `scan_skills(workspace_root)` → `list[dict]` — walks `<workspace>/skills/`, parses YAML frontmatter, applies all eligibility rules, returns `{name, description, location, meta}` dicts
- `format_skills_for_prompt(skills)` → `str` — builds the `<available_skills>` XML block; compresses home-dir paths to `~/`; enforces 150-skill and 30,000-char limits

**Eligibility rules (all must pass unless `always: true`):**
| Rule | Effect |
|---|---|
| `enabled: false` | excluded |
| `disable-model-invocation: true` | excluded (user-only slash-cmd skill) |
| `always: true` | bypasses all remaining checks |
| `requires.anyBins` | excluded if none of the listed binaries exist on PATH |
| `requires.env` | excluded if any listed env var is absent |
| `os` | excluded if current OS not in list; empty list = all OSes |

**Discovery limits:**
- `maxCandidatesPerRoot = 300` — directory scan cap
- `maxSkillsLoaded = 200` — total skills cap
- `maxSkillFileBytes = 256 KB` — oversized SKILL.md files skipped
- Directories starting with `_` (e.g. `_template/`) are always skipped

**Mandatory instruction injected into system prompt:**
```
## Skills (mandatory)

Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: read its SKILL.md at <location>
  using the `read` tool, then follow it.
- If multiple could apply: choose the most specific one, then read and follow it.
- If none clearly apply: do not read any SKILL.md.

Constraints:
  - Never read more than one skill up front.
  - Only read after selecting — never speculatively.
  - Skills live at: <workspace>/skills/<skill-name>/SKILL.md
```

**Skill template:** `skills/_template/SKILL.md` — canonical starting point for new skills. Copy the folder, fill in the YAML frontmatter (`name`, `description`, eligibility fields) and four sections (`When to use`, `Steps`, `Examples`, `Notes`).

**New dependency** (`requirements.txt`): `pyyaml` (YAML frontmatter parsing; graceful degradation if absent — all skills treated as eligible)

**Test suite:** `agent-design/tests/test_skill_use.py` — 48 checks, all passing. Runs directly: `python agent-design/tests/test_skill_use.py`
- `_parse_frontmatter`: valid YAML, no fence, empty block, malformed YAML (no crash), unclosed fence
- `_is_eligible`: empty meta, `enabled: false`, `disable-model-invocation`, `always: true` bypasses binary, missing binary, present binary, missing env var, present env var, OS mismatch, OS match, empty OS list
- `scan_skills`: empty dir, no dir, `_template` skipped, valid skill, missing SKILL.md, no frontmatter (included), `disable-model-invocation` excluded, multiple skills, oversized file
- `format_skills_for_prompt`: empty list, single skill, 150-skill cap, 30k-char budget, home-dir path compression
- `build_skill_section`: mandatory header, skill present, empty skills valid, constraint text

---

### Renamed — `agent-design/prompt_compaction.py` → `agent-design/memory_compaction.py`

Renamed for clarity — the module compacts the agent's *memory* (message history), not the prompt itself. Test file renamed accordingly.

**Deleted:** `agent-design/prompt_compaction.py`, `agent-design/tests/test_prompt_compaction.py`
**Added:** `agent-design/memory_compaction.py`, `agent-design/tests/test_memory_compaction.py`

No functional changes — only the filenames changed.

---

### Added — `agent-design/memory_compaction.py` (rolling-window context compaction)

Implements automatic context compaction for the agent loop. When the message history crosses a configurable token threshold, the full history is summarised by an external model (GPT-5.2) and the context is rebuilt as `[compacted_state, *bridge?, *tail]`.

**Core file:** `agent-design/memory_compaction.py`

**Public API:**
- `maybe_compact(messages, *, api_key, level, config)` — main entry point; checks threshold, runs compaction if needed, returns `(new_messages, CompactionResult)`
- `should_compact(messages, config)` → `(needs_compact, estimated_tokens, threshold_tokens)` — pure threshold check, no side effects
- `run_compaction(messages, *, api_key, level, config)` → `str` — calls OpenAI and returns raw compacted state text
- `apply_compaction(messages, compacted_text, config)` → `list[dict]` — rebuilds the message list; inserts a bridge assistant turn when needed to maintain strict user/assistant alternation
- `estimate_tokens(messages)` → `int` — token count via tiktoken (`cl100k_base`); falls back to `len(text) // 4` only on encode failure

**Config (`CompactionConfig` dataclass):**
| field | default | description |
|---|---|---|
| `max_context_tokens` | `400_000` | GPT-5.2 context window |
| `threshold_ratio` | `0.90` | trigger at 90% capacity |
| `keep_last_n` | `2` | messages retained verbatim after the compacted block |
| `model` | `"gpt-5.2"` | compaction model |
| `compaction_max_tokens` | `4096` | max tokens in the compaction response |

**Compaction levels (`CompactionLevel`):**
- `"orchestrator"` — extracts: original task, current plan, TODO checklist, progress summary, delegations log, critical values, subagent states, errors & dead ends, next step, open questions
- `"computer"` — extracts: browsing objective, current location, session state, critical values, navigation history (compressed), data collected, errors & dead ends, next action

**Result types (discriminated on `status`):**
- `CompactionResultSkipped` — threshold not crossed; `estimated_tokens`, `threshold_tokens`
- `CompactionResultDone` — compaction ran; `estimated_tokens_before`, `messages_before`, `messages_after`, `compacted_text_preview` (first 120 chars)
- `CompactionResultError` — failure, original list returned; `error_code`, `error_message`

**Error codes:** `API_ERROR`, `DEPENDENCY_MISSING`, `EMPTY_HISTORY`, `INTERNAL`

**Key behaviours:**
- On any failure `maybe_compact` returns the original `messages` list unchanged — the agent loop is never left without a valid context
- Turn-alternation fix: if `tail[0].role == "user"`, a minimal `[Context restored from compacted state.]` bridge assistant message is inserted between the compacted block and the tail
- `estimate_tokens` imports `tiktoken` at module level (`_TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")`); char-count fallback is only reached if the encode call itself raises

**New dependencies** (`requirements.txt`): `openai`, `tiktoken`

**Test suite:** `agent-design/tests/test_memory_compaction.py` — 19 cases, all checks passing
- `_extract_text`: plain string, list with text + tool_use + tool_result blocks
- `_serialize_history`: string messages, tool_use/tool_result rendering
- `estimate_tokens`: string messages, list messages, tiktoken-absent char fallback
- `should_compact`: below threshold, above threshold
- `apply_compaction`: basic keep_last_n=2, tail starts with assistant (no bridge), fewer messages than keep_last_n, marker prefix
- `maybe_compact`: empty history, skipped, done (mocked API), DEPENDENCY_MISSING, API_ERROR
- `run_compaction`: `level="computer"` uses computer system prompt

---

### Added — `tools/snapshot`, `tools/tts`, `tools/image_gen`

Three new Tier-2 tools. All follow the standard `tools/<name>/` layout.

#### `tools/snapshot` — desktop screenshot

Captures a screenshot via Pillow's `ImageGrab` and saves it to `.agent/snapshots/`. Optionally returns the image as a base64 string for LLM vision.

- `snapshot_tool.py` — `snapshot_command(params, *, workspace_root, agent_session_id)`
- `snapshot_types.py` — `SnapshotParams` (`monitor`, `region`, `format`, `include_base64`); `SnapshotResultDone` / `SnapshotResultError`
- **Parameters:** all optional — `monitor` (default `0` = all screens), `region` (`[x, y, w, h]`), `format` (`png`/`jpeg`, default `png`), `include_base64` (default `true`)
- **Error codes:** `capture_failed`, `save_failed`, `invalid_region`, `dependency_missing`
- **Audit events:** `snapshot.done`, `snapshot.error` → `.agent/audit/snapshot-{date}.jsonl`
- **Test suite:** `tools/snapshot/test_snapshot.py` — 10 tests, 22/22 checks passing

#### `tools/tts` — text-to-speech via Inworld

Synthesises speech using the Inworld TTS API (`POST https://api.inworld.ai/tts/v1/voice`) and saves the result as an MP3. No new dependencies — uses stdlib `urllib.request`, `base64`, `json`.

- `tts_tool.py` — `tts_command(params, *, workspace_root, agent_session_id)`
- `tts_types.py` — `TtsParams` (`text`, `voice_id`, `model_id`); `TtsResultDone` / `TtsResultError`
- **Parameters:** `text` (required), `voice_id` (default `"Ashley"`), `model_id` (default `"inworld-tts-1.5-max"`)
- **Auth:** `Authorization: Basic {INWORLD_API_KEY}` — key read from env or `.env` file
- **Error codes:** `not_configured`, `api_error`, `save_failed`
- **Audit events:** `tts.done`, `tts.error` → `.agent/audit/tts-{date}.jsonl`
- **Test suite:** `tools/tts/test_tts.py` — 7 tests, 24/24 checks passing

#### `tools/image_gen` — image generation via Gemini

Generates an image from a text prompt using the `google-genai` SDK (model `gemini-3.1-flash-image-preview`) and saves it as a PNG.

- `image_gen_tool.py` — `image_gen_command(params, *, workspace_root, agent_session_id)`
- `image_gen_types.py` — `ImageGenParams` (`prompt`, `size`, `aspect_ratio`); `ImageGenResultDone` / `ImageGenResultError`
- **Parameters:** `prompt` (required), `size` (default `512`), `aspect_ratio` (enum, default `"1:1"`)
- **Auth:** `GEMINI_API_KEY` read from env or `.env` file
- **Error codes:** `not_configured`, `api_error`, `save_failed`, `no_image_in_response`, `dependency_missing`
- **Audit events:** `image_gen.done`, `image_gen.error` → `.agent/audit/image_gen-{date}.jsonl`
- **Test suite:** `tools/image_gen/test_image_gen.py` — 10 tests, 28/28 checks passing

**New env vars** (documented in `.env.example`): `INWORLD_API_KEY`, `GEMINI_API_KEY`

**New dependencies** (`requirements.txt`): `Pillow`, `google-genai`

---

### Refactored — remove `env_loader.py` and per-tool `config.py` files

The intermediate `tools/env_loader.py` wrapper and the `config.py` files in `tools/tts/` and `tools/image_gen/` were unnecessary indirection. Replaced with direct `load_dotenv` + `os.getenv` calls inlined in each tool function.

**Deleted:** `tools/env_loader.py`, `tools/tts/config.py`, `tools/image_gen/config.py`

**Updated:** `comm_channels/telegram/config.py` — now imports `load_dotenv` directly instead of going through `env_loader`

**New dependency** (`requirements.txt`): `python-dotenv`

---

### Updated — `tools/__init__.py` (11 tools)

`ALL_TOOLS` now exposes all eleven tools:

```python
from tools import ALL_TOOLS  # len == 11
# exec, process, read, write, edit, remember, ping, send_media, snapshot, tts, image_gen
```

---

### Added — `tools/send_media` (`send_user_media` tool)

New tool for sending media files (photo, document, video, audio) to the user. Reads from the local workspace and uploads via the configured medium.

**Core files:**
- `tools/send_media/send_media_tool.py` — `send_media_command(params, *, workspace_root, agent_session_id)`; resolves and safety-checks path via `file_safety.resolve_path()`, dispatches to medium, audits outcome
- `tools/send_media/send_media_types.py` — `SendMediaParams` dataclass; discriminated-union results (`SendMediaResultSent`, `SendMediaResultError`)
- `tools/send_media/__init__.py` — `TOOL_DEFINITION` JSON schema for LLM function calling

**Backend additions (`comm_channels/`):**
- `telegram/client.py` — new `upload_media(token, method, chat_id, field_name, file_bytes, filename, *, caption, parse_mode, http_timeout)` — builds `multipart/form-data` body from scratch using stdlib only (`mimetypes`, `uuid`, `urllib.request`); no external dependencies
- `telegram/sender.py` — new `send_media(params, cfg, resolved_path)` — maps `media_type → (API method, field name)`, reads file bytes, escapes caption via `escape_mdv2()`, calls `upload_media()`
- `terminal/channel.py` — new `terminal_send_media(params)` — prints `[MEDIA:TYPE] path — caption` to stdout

**Parameters:** `path`, `media_type` (required: `photo`/`document`/`video`/`audio`); `caption`, `medium` (default `telegram`)

**Media type → Telegram API mapping:**
| media_type | API method | field name |
|---|---|---|
| `photo` | `sendPhoto` | `photo` |
| `document` | `sendDocument` | `document` |
| `video` | `sendVideo` | `video` |
| `audio` | `sendAudio` | `audio` |

**Return variants** (discriminated on `status`):
- `sent` — `message_id`
- `error` — `error_code`, `detail`

**Error codes:** `not_configured`, `file_not_found`, `file_blocked`, `send_failed`, `invalid_params`

**Audit events:** `media.file_error`, `media.done` (written to `.agent/audit/ping-{date}.jsonl`)

**Test suite:** `tools/send_media/test_send_media.py` — 13 cases, 32 checks, 32/32 passing
- File not found, blocked path (`.env`), terminal photo (output format), terminal document with caption, terminal no caption, Telegram photo/document/video/audio correct method + field, caption MarkdownV2-escaped, not_configured, upload failure → send_failed, audit event written

---

### Refactored — `ping_user` promoted to `tools/ping/`

`comm_channels/ping_tool.py` (the tool entry point) moved into the standard `tools/<name>/` layout. `comm_channels/` is now a pure backend implementation package.

**New files:**
- `tools/ping/ping_tool.py` — `ping_command()` (renamed from `ping_user`); all backend imports continue to point at `comm_channels.*`
- `tools/ping/__init__.py` — `TOOL_DEFINITION` + exports (schema moved from `comm_channels/__init__.py`)
- `tools/ping/test_ping.py` — all 24 tests moved here; imports updated to `ping_command` + absolute `comm_channels.*` paths

**Modified files:**
- `comm_channels/__init__.py` — `TOOL_DEFINITION` removed; package is now backend-only
- `comm_channels/test_ping.py` — replaced with a one-line redirect comment pointing to `tools/ping/test_ping.py`
- `tools/__init__.py` — `PING_TOOL` and `SEND_MEDIA_TOOL` added; `ALL_TOOLS` now has 8 entries

---

### Updated — `tools/__init__.py`

Now exposes all eight tools at the package root:

```python
from tools import ALL_TOOLS  # list of all 8 TOOL_DEFINITION dicts
# ['exec', 'process', 'read', 'write', 'edit', 'remember', 'ping_user', 'send_user_media']
```

---

### Added — `comm_channels/ping_user` (user communication layer)

Complete implementation of the `ping_user(msg, type, medium=)` tool — the agent's voice. Sends messages and blocking queries to the user via Telegram or terminal.

**Core files:**
- `comm_channels/ping_tool.py` — main dispatcher: validates params → routes to medium → audits outcome
- `comm_channels/ping_types.py` — `PingParams` dataclass and the discriminated-union result variants (`PingResultSent`, `PingResultResponse`, `PingResultError`)
- `comm_channels/templates.py` — per-type format strings for both mediums; `escape_mdv2()` escapes all user-supplied text for safe inclusion in Telegram MarkdownV2 messages
- `comm_channels/_state.py` — thread-safe load/save of `.agent/comm/telegram_state.json`; persists `last_update_message_id` for in-place editing of update messages
- `comm_channels/audit.py` — thread-safe JSONL audit log at `.agent/audit/ping-{date}.jsonl`
- `comm_channels/__init__.py` — `TOOL_DEFINITION` JSON schema for LLM function calling

**Telegram subpackage (`comm_channels/telegram/`):**
- `config.py` — loads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `os.environ` or a `.env` file at the workspace root; raises `ConfigError` on missing vars
- `client.py` — thin `urllib.request` wrapper (zero extra deps); named methods: `send_message`, `edit_message_text`, `get_updates`, `answer_callback_query`; all route through `_call()` which raises `TelegramAPIError` on failure
- `sender.py` — four send functions (`send_update`, `send_chat`, `send_query_msg`, `send_query_options`) + long-poll loops (`_poll_for_text_reply`, `_poll_for_callback`)

**Terminal subpackage (`comm_channels/terminal/`):**
- `channel.py` — stdlib `print`/`input` fallback; works without any config or network

**Parameters:** `msg`, `type` (required); `medium` (default `telegram`), `options`, `title`, `timeout` (default 120s), `edit_last_update` (default `True`)

**Message types:**
| type | direction | Telegram mechanics |
|---|---|---|
| `update` | one-way | `editMessageText` in-place (falls back to `sendMessage` on failure); persists `last_update_message_id` in state |
| `chat` | one-way | `sendMessage` plain text |
| `query:msg` | blocking | `sendMessage` + `ForceReply`; polls `getUpdates` for a message replying to the sent one |
| `query:options` | blocking | `sendMessage` + `InlineKeyboardMarkup`; polls `getUpdates` for `callback_query`; calls `answerCallbackQuery` immediately on match |

**Return variants** (discriminated on `status`):
- `sent` — `message_id`
- `response` — `response` (user's text or selected option label), `message_id`
- `error` — `error_code`, `detail`

**Error codes:** `not_configured`, `timeout`, `send_failed`, `invalid_params`, `medium_error`

**Key behaviours:**
- All four message types go to the same `TELEGRAM_CHAT_ID` — no separate channel vs DM split
- `update` edits the previous message in-place when `edit_last_update=True`; Telegram's "message is not modified" 400 is treated as success (not an error)
- Poll loops advance `offset` for every update (including non-matching ones) to prevent re-delivery; offset is local to each call, not persisted
- `answerCallbackQuery` is called immediately on callback match to dismiss the Telegram button spinner (must happen within ~10 s)
- `escape_mdv2()` uses a single compiled regex to escape all 19 MarkdownV2 special characters in user-supplied content; structural template markup (`*bold*`, `_italic_`) is not escaped

**Audit events:** `ping.invalid_params`, `ping.done`

**Test suite:** `comm_channels/test_ping.py` — 24 cases, 57 checks, 57/57 passing
- Missing options list, missing env vars, terminal update (with/without title), terminal chat, terminal query:msg (mocked stdin), terminal query:options (valid / out-of-range / non-numeric / stdin closed), Telegram send_update (no prior state / edit succeeds / "not modified" / edit fails→fallback / edit_last_update=False), Telegram chat (success / send_failed), Telegram query:msg (reply arrives / timeout), Telegram query:options (callback arrives / timeout), state file corrupt JSON recovery, audit file written, escape_mdv2 special characters

---

### Added — `.env.example`

Template environment file documenting the two required Telegram variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) with inline instructions for finding each value via `getUpdates`.

---

### Fixed — single `TELEGRAM_CHAT_ID` (design simplification)

Initial design used two separate env vars (`TELEGRAM_CHANNEL_ID` for `update` type, `TELEGRAM_USER_CHAT_ID` for all others). Collapsed to a single `TELEGRAM_CHAT_ID` used by all four message types, matching the real-world usage pattern where the agent talks to one person in one chat.

---

### Added — `tools/exec` (terminal interaction layer)

Complete implementation of the `exec(command, intent)` tool — the single gateway through which the agent touches the host system.

**Core files:**
- `tools/exec/exec_tool.py` — main entry point; validates → safety-checks → spawns → shapes result
- `tools/exec/exec_types.py` — all dataclasses: `ExecParams`, `ExecBase`, and the discriminated-union result variants (`ExecResultDone`, `ExecResultRunning`, `ExecResultFailed`, `ExecResultKilled`, `ExecResultError`)
- `tools/exec/supervisor.py` — `ProcessSupervisor` singleton: process registry, state machine (`pending → running → done | killed`), watchdog threads, GC (10-min retention), and session ceiling (1-hour hard kill)
- `tools/exec/buffer.py` — `CircularLineBuffer`: 10k-line / 4MB in-memory ring buffer with continuous disk spillover to `.agent/sessions/{session_id}/stdout.log`
- `tools/exec/safety.py` — intent validator (min 10 chars, no generics, `rm` requires deletion mention), 13-pattern command blocklist (rm -rf /, fork bomb, mkfs, dd, curl-pipe-shell, etc.), env sanitizer (protected keys dropped, secret keys flagged for log redaction)
- `tools/exec/shell.py` — cross-platform shell detection and argv builder; injects `CI=1`, `NO_COLOR=1`, `TERM=dumb`, `AGENT_SESSION_ID`, `AGENT_EXEC_ID`, `AGENT_WORKSPACE`
- `tools/exec/output.py` — ANSI escape-code stripper, tail-preferred truncation (32KB / 2000 lines) with disk-log path note
- `tools/exec/audit.py` — thread-safe JSONL audit log at `.agent/audit/exec-{date}.jsonl`
- `tools/exec/__init__.py` — `TOOL_DEFINITION` JSON schema for LLM function calling

**Parameters:** `command`, `intent` (required), `cwd`, `env`, `yieldMs` (default 10s), `timeout`, `background`, `shell`, `stdin`, `stripAnsi`

**Return variants** (discriminated on `status`):
- `done` — `exit_code`, `stdout`, `stderr`, truncation info
- `running` — `session_id`, `tail`, `tail_lines`, `lines_so_far`, `hint`
- `failed` — `exit_code`, `stdout`, `stderr`, human-readable `diagnosis`
- `killed` — `killed_by`, `timeout_ms`, `stdout`
- `error` — `error_code`, `error_message`, `blocked_pattern`

**Test suite:** `tools/exec/test_exec.py` — 20 cases, 58 checks, 58/58 passing
- Smoke test, non-zero exit, async yield, blocklist (rm -rf /, curl-pipe), intent validation (too short, generic, rm without deletion mention), invalid cwd, stdin pre-feed, background mode, env injection, custom env, protected env drop, secret redaction, ANSI stripping, output truncation, stderr capture, audit log, disk spillover log

---

### Added — `tools/process` (long-running process management)

Companion tool to `exec()` for managing background processes via a shared `ProcessSupervisor`.

**Core files:**
- `tools/process/process_tool.py` — routes 7 actions to the supervisor
- `tools/process/proc_types.py` — `ProcessParams` dataclass
- `tools/process/__init__.py` — `TOOL_DEFINITION` JSON schema for LLM function calling

**Actions:**
| Action | Description |
|--------|-------------|
| `poll` | Current state + stdout tail; hint guides next action |
| `kill` | SIGTERM → 5s grace → SIGKILL |
| `send-keys` | Write string to process stdin (optional newline) |
| `submit` | Alias for `send-keys` with `press_enter=True` |
| `close-stdin` | Send EOF to process stdin pipe |
| `list` | All sessions with optional state filter (`running`/`done`/`killed`/`all`) |
| `get-log` | Paginated raw log read from disk (byte `offset` + `limit`) |

**Test suite:** `tools/process/test_process.py` — 13 cases, 46 checks, 46/46 passing
- Poll running/until-done, kill live process, kill already-finished process, send-keys, submit, close-stdin, list with filter, get-log, get-log pagination, expired session, missing session_id errors

---

### Added — `tools/file_safety.py` (shared path validation)

Single shared module imported by all three file-op tools.

- `resolve_path(path, workspace_root)` — resolves symlinks, enforces workspace containment via `Path.is_relative_to()`, checks against sensitive-file blocklist
- `is_binary_content(data, sample_size=8192)` — null-byte heuristic matching git's binary detection
- `_file_ops_audit_lock` — module-level `threading.Lock()` shared by all three `audit.py` files so concurrent writes to the same daily JSONL file are race-free
- Sensitive-file blocklist: `.env*`, `credentials.json`, SSH private keys (`id_rsa` etc.), `.pem`/`.key` files, `.ssh/` directory, `.git/config`
- Uses `[\\/]` in all regex patterns for cross-platform path separator handling

---

### Added — `tools/read` (file reading)

`read(path)` — the agent's eyes. Returns file content with metadata; supports pagination, binary handling, and encoding fallback.

**Core files:**
- `tools/read/read_tool.py` — main entry: `read_command(params, *, workspace_root, agent_session_id)`
- `tools/read/read_types.py` — `ReadParams`, `ReadResultDone`, `ReadResultError`, `ReadResult` union; `ReadErrorCode` literal
- `tools/read/audit.py` — JSONL events to `.agent/audit/file-ops-{date}.jsonl`
- `tools/read/__init__.py` — `TOOL_DEFINITION` + `__all__`

**Parameters:** `path` (required), `encoding` (default `utf-8`), `max_bytes` (default 1 MB), `start_line`, `num_lines`, `binary` (`error`/`base64`/`skip`)

**Return variants** (discriminated on `status`):
- `done` — `content`, `encoding`, `size_bytes`, `total_lines`, `lines_returned`, `truncated`, `truncation_note`
- `error` — `error_code`, `error_message`

**Error codes:** `BLOCKED_PATH`, `NOT_FOUND`, `IS_DIRECTORY`, `BINARY_FILE`, `ENCODING_ERROR`, `PERMISSION_DENIED`, `INTERNAL`

**Key behaviours:**
- Empty file → `done` (not an error)
- `start_line` past EOF → `done`, `content=""`, `lines_returned=0` (clean pagination termination)
- `UnicodeDecodeError` → falls back to `latin-1`; `LookupError` (bad encoding name) → immediate `ENCODING_ERROR` with no fallback
- Binary with `binary="base64"` → `base64.b64encode`, `encoding="base64"` in result

**Audit events:** `read.blocked`, `read.start`, `read.done`, `read.error`

**Test suite:** `tools/read/test_read.py` — 17 cases, 49 checks, 49/49 passing

---

### Added — `tools/write` (file writing)

`write(path, content)` — the agent's hands. Creates or fully overwrites files; atomic by default.

**Core files:**
- `tools/write/write_tool.py` — main entry: `write_command(params, *, workspace_root, agent_session_id)`
- `tools/write/write_types.py` — `WriteParams`, `WriteResultDone`, `WriteResultError`, `WriteResult` union
- `tools/write/audit.py` — JSONL events to shared `file-ops-{date}.jsonl`
- `tools/write/__init__.py` — `TOOL_DEFINITION` + `__all__`

**Parameters:** `path`, `content` (required), `encoding` (default `utf-8`), `create_parents` (default `True`), `overwrite` (default `True`), `atomic` (default `True`), `max_bytes` (default 10 MB)

**Return variants:**
- `done` — `bytes_written`, `lines_written`, `created`, `overwritten`, `atomic`
- `error` — `error_code`, `error_message`

**Error codes:** `BLOCKED_PATH`, `FILE_EXISTS`, `SIZE_LIMIT_EXCEEDED`, `PARENT_NOT_FOUND`, `ENCODING_ERROR`, `PERMISSION_DENIED`, `INTERNAL`

**Key behaviours:**
- Content encoded upfront before touching disk — size and encoding errors caught before any filesystem mutation
- Atomic write: temp file (`.~{name}.{uuid8}.tmp` in same directory) + `os.replace()` — atomic on both POSIX and Windows; temp cleaned up on failure with `missing_ok=True`
- `create_parents=True` (default) creates the full directory tree via `mkdir(parents=True, exist_ok=True)`

**Audit events:** `write.blocked`, `write.start`, `write.done`, `write.error`

**Test suite:** `tools/write/test_write.py` — 16 cases, 47 checks, 47/47 passing

---

### Added — `tools/edit` (surgical file editing)

`edit(path, old, new)` — replaces an exact string in a file without rewriting the whole thing. Always returns a unified diff.

**Core files:**
- `tools/edit/edit_tool.py` — main entry: `edit_command(params, *, workspace_root, agent_session_id)`
- `tools/edit/edit_types.py` — `EditParams`, `EditResultDone`, `EditResultError`, `EditResult` union
- `tools/edit/audit.py` — JSONL events to shared `file-ops-{date}.jsonl`
- `tools/edit/__init__.py` — `TOOL_DEFINITION` + `__all__`

**Parameters:** `path`, `old`, `new` (required), `encoding` (default `utf-8`), `allow_multiple` (default `False`), `dry_run` (default `False`), `atomic` (default `True`)

**Return variants:**
- `done` — `replacements_made`, `lines_added`, `lines_removed`, `dry_run`, `diff_preview`
- `error` — `error_code`, `error_message`

**Error codes:** `BLOCKED_PATH`, `NOT_FOUND`, `IS_DIRECTORY`, `OLD_NOT_FOUND`, `OLD_AMBIGUOUS`, `ENCODING_ERROR`, `PERMISSION_DENIED`, `INTERNAL`

**Key behaviours:**
- `diff_preview` (unified diff via `difflib.unified_diff`) is **always** populated, even on real writes — agent can verify the change without re-reading the file
- `OLD_AMBIGUOUS` error message includes the occurrence count to help the agent tighten the `old` string
- `OLD_NOT_FOUND` error message explicitly says "Ensure exact match including whitespace and newlines"
- `dry_run=True` computes and returns the diff but skips the write; emits `edit.dry_run` audit event (not `edit.done`)
- Same atomic write pattern (tmp + `os.replace()`) as `write_tool`

**Audit events:** `edit.blocked`, `edit.start`, `edit.done`, `edit.dry_run`, `edit.error`

**Test suite:** `tools/edit/test_edit.py` — 17 cases, 43 checks, 43/43 passing

---

### Added — `tools/remember` (long-term semantic memory)

`remember(action, ...)` — persistent memory across sessions using ChromaDB vector embeddings.

**Core files:**
- `tools/remember/remember_tool.py` — dispatcher for `store`, `query`, `list`, `delete` actions; per-`chroma_dir` store registry (thread-safe, test-isolated)
- `tools/remember/remember_types.py` — `RememberParams`, `MemoryHit`, and discriminated-union result variants (`RememberResultStored`, `RememberResultQueried`, `RememberResultListed`, `RememberResultDeleted`, `RememberResultError`)
- `tools/remember/audit.py` — thread-safe JSONL audit log at `.agent/audit/memory-{date}.jsonl`
- `tools/remember/__init__.py` — `TOOL_DEFINITION` JSON schema for LLM function calling

**Memory layer (`memory/long_term_mem/store.py`):**
- `LongTermMemStore` — thread-safe wrapper around ChromaDB `PersistentClient`; lazy-initialised on first use
- Stores documents with `timestamp`, `session_id`, `tags` (CSV) metadata
- `store()` → `(memory_id, iso_timestamp)`; `query()` → `(hits, total)`; `list_all()` → `(items, total)`; `delete()` → `bool`
- Data persists at `{workspace_root}/.agent/memory/chroma/`

**Parameters:** `action` (required); `content` (store), `query` + `n_results` (query, default 5, clamped 1–50), `memory_id` (delete), `tags` (store, optional)

**Return variants** (discriminated on `status`):
- `stored` — `memory_id`, `content_preview`, `tags`, `timestamp`
- `queried` — `query`, `hits` (list of `MemoryHit`), `total_in_collection`
- `listed` — `memories` (list of `MemoryHit`), `total`
- `deleted` — `memory_id`
- `error` — `error_code`, `error_message`

**Error codes:** `MISSING_CONTENT`, `MISSING_QUERY`, `MISSING_MEMORY_ID`, `MEMORY_NOT_FOUND`, `CHROMA_UNAVAILABLE`, `CHROMA_ERROR`, `INVALID_ACTION`, `INTERNAL`

**Test suite:** `tools/remember/test_remember.py` — 17 cases, 60 checks, 60/60 passing
- `CHROMA_UNAVAILABLE` (no chromadb), store smoke test, `MISSING_CONTENT` (None/empty), query smoke test, `MISSING_QUERY`, n_results clamping, query on empty collection, list smoke test, list on empty collection, delete smoke test, `MEMORY_NOT_FOUND`, `MISSING_MEMORY_ID`, persistence across store instances, audit log (JSONL + all event types), tags round-trip, `INVALID_ACTION`, unicode content round-trip

---

### Fixed — chromadb / onnxruntime install on Windows

- **C++ redistributable required** — `onnxruntime` (pulled in by chromadb's default embedding function) requires the MSVC runtime. Install via Visual Studio Build Tools.
- **numpy pin** — `onnxruntime 1.17` is incompatible with numpy 2.x. Pinned `numpy<2` in `requirements.txt`.
- **venv rebuild** — existing venv had conflicting package state after pin changes; required full teardown and recreation.

---

### Updated — `tools/__init__.py` (initial — 6 tools)

Exposed the first six tools at the package root:

```python
from tools import ALL_TOOLS  # list of all 6 TOOL_DEFINITION dicts
```

Exports: `exec_command`, `process_command`, `read_command`, `write_command`, `edit_command`, `remember_command` and their corresponding `*Params` classes and `*_TOOL` definition dicts.

---

### Fixed (during read/write/edit implementation)

- **Windows line endings in tests** — `Path.write_text()` on Windows uses `\r\n` by default, causing content equality checks to fail. Fixed by using `write_bytes(content.encode("utf-8"))` throughout all test files for precise binary control.
- **Encoding fallback too eager** — `LookupError` (invalid encoding name like `"utf-99"`) and `UnicodeDecodeError` (valid encoding, bad bytes) were caught by the same `except` clause, causing the latin-1 fallback to silently succeed on unknown encoding names. Fixed by splitting into separate `except LookupError` (immediate `ENCODING_ERROR`) and `except UnicodeDecodeError` (latin-1 fallback) handlers.
- **Direct test execution (`python test_read.py`)** — relative imports fail when a file is run directly because Python has no `__package__` context. Fixed by adding a `__package__` shim at the top of each test file (before the relative imports) that sets `sys.path` and `__package__` when `__name__ == "__main__" and __package__ is None`. Both `python test_*.py` and `python -m tools.*.test_*` now work.

---

### Fixed (during exec/process implementation)

- **`types.py` name collision** — renamed to `exec_types.py` and `proc_types.py` to prevent Python's import machinery from finding our files when resolving the stdlib `types` module, causing a circular-import `MappingProxyType` error.
- **Windows cmd semicolon quoting** — `subprocess.list2cmdline` wraps commands in extra quotes, causing semicolons in Python one-liners (e.g. `import time; time.sleep(30)`) to be treated as `cmd.exe` command separators. Fixed by using `shell=True` + raw command string when `platform == "win32" and shell_name == "cmd"`.
- **Windows temp dir file lock** — daemon reader threads held log file handles open when `TemporaryDirectory.__exit__` tried to delete them. Fixed by joining reader threads in `_kill_entry`, adding `ignore_cleanup_errors=True` to test temp dirs, and killing all running sessions before exiting the `with` block.
- **stdin deadlock** — `sys.stdin.read()` in test blocked forever because the stdin pipe is intentionally kept open for `send-keys`. Fixed by switching the test command to `print(input())` with a newline-terminated stdin string, so the process reads one line and exits cleanly.
- **`kw_only=True` missing on dataclasses** — subclasses of `ExecBase` overrode `status` with a default while the parent class had non-default fields after it, causing a `TypeError` at class definition time. Fixed by adding `kw_only=True` to all result dataclass decorators.
- **Watchdog race condition** — watchdog thread could overwrite `state="killed"` back to `state="done"` after `_kill_entry` had already set it. Fixed by guarding `if entry.meta.state != "killed": entry.meta.state = "done"` in the watchdog.
- **`_kill_entry` not returning `bool`** — `kill()` always returned `None`, so `process_tool.py` could never distinguish a successful kill from killing an already-dead process. Fixed by making `_kill_entry` return `bool` and propagating it through `kill()`.
- **Kill on finished process race** — `_kill_entry` guarded against `state in ("killed", "error", "done")` but the state was still `"running"` in the brief window between process exit and the watchdog updating it. Fixed by also checking `proc.poll() is not None`.

---

## [0.0.1] — initial commit

- Rough architecture plans extracted from open-claw, filtered for Crunchy-Neck-Agent scope
- `Tools-To-Add.md` listing Tier 1 and Tier 2 tools
