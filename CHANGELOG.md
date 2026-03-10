# Changelog

All notable changes to Crunchy-Neck-Agent are documented here.

---

## [Unreleased] — 2026-03-10

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

### Updated — `tools/__init__.py`

Now exposes all five tools at the package root:

```python
from tools import ALL_TOOLS  # list of all 5 TOOL_DEFINITION dicts
```

Exports: `exec_command`, `process_command`, `read_command`, `write_command`, `edit_command` and their corresponding `*Params` classes and `*_TOOL` definition dicts.

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
