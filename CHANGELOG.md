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

### Fixed (during implementation)

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
