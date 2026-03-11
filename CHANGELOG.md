# Changelog

All notable changes to Crunchy-Neck-Agent are documented here.

---

## [Unreleased] — 2026-03-11

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
