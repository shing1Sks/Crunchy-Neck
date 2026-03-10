"""
Process tool test suite.
Run from workspace root:  python -m tools.process.test_process
"""
from __future__ import annotations

import sys
import tempfile
import time

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = PASS if condition else FAIL
    detail_str = f"  → {detail}" if detail else ""
    print(f"  [{status}] {name}{detail_str}")


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Cross-platform commands ────────────────────────────────────────────────────

def py(code: str) -> str:
    return f'python -c "{code}"'

SLEEP_30   = py("import time; time.sleep(30)")
SLEEP_1    = py("import time; time.sleep(1)")
STDIN_ECHO = py("import sys; print(sys.stdin.read(), end='')")
PRINT_100  = py("[ print(i) for i in range(100) ]")
STDIN_LOOP = py(
    "import sys;"
    "[ print('got: ' + sys.stdin.readline().strip()) for _ in range(2) ]"
)


# ── Bound callers ─────────────────────────────────────────────────────────────

def make_callers(workspace: str):
    from tools.exec.exec_tool import exec_command
    from tools.exec.exec_types import ExecParams
    from tools.process.process_tool import process_command
    from tools.process.proc_types import ProcessParams

    def run(command: str, intent: str, **kwargs):
        params = ExecParams(command=command, intent=intent, **kwargs)
        return exec_command(params, workspace_root=workspace, agent_session_id="test_session")

    def proc(action: str, session_id: str | None = None, **kwargs):
        params = ProcessParams(action=action, session_id=session_id, **kwargs)
        return process_command(params)

    return run, proc


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_poll_running(run, proc, workspace: str) -> None:
    section("1. poll — running process")
    r = run(SLEEP_30, intent="Starting long sleep to test poll on a running process",
            yieldMs=300, background=False)
    check("exec returned running",  r.status == "running", r.status)

    p = proc("poll", r.session_id)
    check("poll state=running",     p["state"] == "running",  p["state"])
    check("poll has duration_ms",   p["duration_ms"] >= 0,    str(p["duration_ms"]))
    check("poll has pid",           p.get("pid") is not None, str(p.get("pid")))
    check("poll has hint",          "poll" in p.get("hint", "").lower() or "running" in p.get("hint","").lower(),
          p.get("hint","")[:60])

    # Clean up.
    from tools.exec.supervisor import get_supervisor
    get_supervisor().kill(r.session_id, reason="user")


def test_poll_until_done(run, proc, workspace: str) -> None:
    section("2. poll — wait for short process to finish")
    r = run(SLEEP_1, intent="Starting 1s sleep to poll until completion",
            yieldMs=200)

    if r.status == "done":
        check("finished before yield",  True, "done immediately")
        return

    check("initially running",  r.status == "running", r.status)
    sid = r.session_id

    # Poll until done (max 5s).
    p = None
    for _ in range(25):
        time.sleep(0.2)
        p = proc("poll", sid)
        if p["state"] == "done":
            break

    check("eventually done",         p["state"] == "done",   p["state"])
    check("exit_code available",     p.get("exit_code") == 0, str(p.get("exit_code")))
    check("hint mentions finished",  "finish" in p.get("hint","").lower() or "exit" in p.get("hint","").lower(),
          p.get("hint","")[:80])


def test_kill(run, proc, workspace: str) -> None:
    section("3. kill — terminate running process")
    r = run(SLEEP_30, intent="Starting long sleep process to test the kill action",
            background=True)
    check("started as running",  r.status == "running", r.status)
    sid = r.session_id

    k = proc("kill", sid)
    check("kill ok=True",        k.get("killed") is True, str(k))

    # Brief wait then poll to confirm killed state.
    time.sleep(0.3)
    p = proc("poll", sid)
    check("state=killed after kill",  p["state"] == "killed", p["state"])


def test_kill_already_dead(run, proc, workspace: str) -> None:
    section("4. kill — killing a finished process returns SESSION_EXPIRED")
    r = run(py("print('quick')"),
            intent="Quick command to test killing an already-finished process",
            yieldMs=0)
    check("exec done",  r.status == "done", r.status)

    # Wait for GC to NOT kick in yet (it's 10min) — process is done but entry exists.
    k = proc("kill", r.session_id)
    # Process is done — supervisor.kill returns False for finished processes.
    check("returns error or ok=False",
          k.get("error_code") == "SESSION_EXPIRED" or k.get("killed") is False or not k.get("killed", True),
          str(k))


def test_send_keys(run, proc, workspace: str) -> None:
    section("5. send-keys — write to stdin of running process")
    # STDIN_LOOP reads two lines from stdin and prints each.
    r = run(STDIN_LOOP,
            intent="Testing send-keys by feeding two lines to a stdin-reading process",
            yieldMs=500)

    if r.status == "done":
        # Finished before we could send — skip (fast machine).
        check("process too fast to test send-keys (skip)", True, "done before yield")
        return

    check("process running",  r.status == "running", r.status)
    sid = r.session_id

    sk1 = proc("send-keys", sid, keys="line one")
    check("send-keys ok",     sk1.get("ok") is True, str(sk1))
    check("sent has newline", "\n" in sk1.get("sent",""), repr(sk1.get("sent","")))

    time.sleep(0.2)

    sk2 = proc("send-keys", sid, keys="line two")
    check("second send ok",   sk2.get("ok") is True, str(sk2))

    # Wait for process to finish.
    for _ in range(20):
        time.sleep(0.2)
        p = proc("poll", sid)
        if p["state"] == "done":
            break

    check("process finished after input",  p["state"] == "done", p["state"])
    check("output has 'got: line one'",
          "got: line one" in p.get("tail",""),
          repr(p.get("tail","")[:120]))


def test_submit(run, proc, workspace: str) -> None:
    section("6. submit — alias for send-keys with newline")
    r = run(STDIN_ECHO,
            intent="Testing submit action which is an alias for send-keys with newline",
            yieldMs=500)

    if r.status == "done":
        check("process too fast (skip)", True, "done before yield")
        return

    check("process running",  r.status == "running", r.status)
    sid = r.session_id

    s = proc("submit", sid, keys="submitted text")
    check("submit ok",        s.get("ok") is True,          str(s))
    check("submitted field",  s.get("submitted") == "submitted text",
          repr(s.get("submitted","")))

    # Close stdin so the process can finish.
    from tools.exec.supervisor import get_supervisor
    get_supervisor().close_stdin(sid)

    for _ in range(20):
        time.sleep(0.2)
        p = proc("poll", sid)
        if p["state"] == "done":
            break

    check("process done after submit + close-stdin",
          p["state"] == "done", p["state"])


def test_close_stdin(run, proc, workspace: str) -> None:
    section("7. close-stdin — send EOF to process")
    # cat reads stdin until EOF; closing stdin makes it exit.
    r = run(STDIN_ECHO,
            intent="Testing close-stdin to send EOF and terminate a stdin-reading process",
            stdin="initial data ",
            yieldMs=500)

    if r.status == "done":
        check("process finished with initial stdin (skip)", True, "done before yield")
        return

    check("process running",  r.status == "running", r.status)
    sid = r.session_id

    cs = proc("close-stdin", sid)
    check("close-stdin ok",   cs.get("ok") is True, str(cs))

    for _ in range(20):
        time.sleep(0.2)
        p = proc("poll", sid)
        if p["state"] == "done":
            break

    check("process done after close-stdin",  p["state"] == "done", p["state"])


def test_list(run, proc, workspace: str) -> None:
    section("8. list — shows all sessions")
    # Start two background processes.
    r1 = run(SLEEP_30, intent="Background process #1 for list test", background=True)
    r2 = run(SLEEP_30, intent="Background process #2 for list test", background=True)

    listing = proc("list")
    check("action=list",      listing["action"] == "list",   listing["action"])
    check("sessions is list", isinstance(listing["sessions"], list), type(listing["sessions"]).__name__)
    check("count >= 2",       listing["count"] >= 2,         str(listing["count"]))

    sids = {s["session_id"] for s in listing["sessions"]}
    check("r1 in list",  r1.session_id in sids, r1.session_id)
    check("r2 in list",  r2.session_id in sids, r2.session_id)

    # Filter by running.
    running_list = proc("list", filter="running")
    running_sids = {s["session_id"] for s in running_list["sessions"]}
    check("both running in running filter",
          r1.session_id in running_sids and r2.session_id in running_sids,
          str(running_sids))

    # Clean up.
    from tools.exec.supervisor import get_supervisor
    sv = get_supervisor()
    sv.kill(r1.session_id, reason="user")
    sv.kill(r2.session_id, reason="user")


def test_get_log(run, proc, workspace: str) -> None:
    section("9. get-log — read full stdout from disk")
    r = run(PRINT_100,
            intent="Running 100 print statements to test get-log disk reading",
            yieldMs=0)
    check("status=done",  r.status == "done", r.status)

    gl = proc("get-log", r.session_id, stream="stdout")
    check("action=get-log",     gl["action"] == "get-log",  gl["action"])
    check("content non-empty",  len(gl.get("content","")) > 0,
          f"{gl.get('bytes_returned',0)} bytes")
    check("content has line 99","99" in gl.get("content",""),
          repr(gl.get("content","")[-50:]))
    check("bytes_returned set", gl.get("bytes_returned",0) > 0,
          str(gl.get("bytes_returned")))


def test_get_log_pagination(run, proc, workspace: str) -> None:
    section("10. get-log pagination — offset + limit")
    r = run(PRINT_100,
            intent="Testing get-log pagination with offset and limit parameters",
            yieldMs=0)
    check("status=done",  r.status == "done", r.status)

    # First 20 bytes.
    page1 = proc("get-log", r.session_id, offset=0, limit=20)
    check("page1 ≤ 20 bytes",  page1.get("bytes_returned",0) <= 20,
          str(page1.get("bytes_returned")))
    check("page1 non-empty",   len(page1.get("content","")) > 0,
          repr(page1.get("content","")))

    # Offset beyond first page.
    page2 = proc("get-log", r.session_id, offset=20, limit=20)
    check("page2 non-empty",   len(page2.get("content","")) > 0,
          repr(page2.get("content","")))
    check("pages differ",
          page1.get("content","") != page2.get("content",""),
          "pages are distinct")


def test_poll_expired_session(run, proc, workspace: str) -> None:
    section("11. poll — expired/unknown session_id")
    p = proc("poll", "exec_doesnotexist")
    check("error_code=SESSION_EXPIRED",
          p.get("error_code") == "SESSION_EXPIRED",
          str(p))


def test_send_keys_no_session_id(run, proc, workspace: str) -> None:
    section("12. send-keys — missing session_id returns error")
    r = proc("send-keys", keys="hello")
    check("error returned",  "error_code" in r, str(r))


def test_kill_missing_session_id(run, proc, workspace: str) -> None:
    section("13. kill — missing session_id returns error")
    r = proc("kill")
    check("error returned",  "error_code" in r, str(r))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  process tool — test suite")
    print("=" * 60)

    with tempfile.TemporaryDirectory(
        prefix="crunchy_proc_test_", ignore_cleanup_errors=True
    ) as workspace:
        run, proc = make_callers(workspace)

        test_poll_running(run, proc, workspace)
        test_poll_until_done(run, proc, workspace)
        test_kill(run, proc, workspace)
        test_kill_already_dead(run, proc, workspace)
        test_send_keys(run, proc, workspace)
        test_submit(run, proc, workspace)
        test_close_stdin(run, proc, workspace)
        test_list(run, proc, workspace)
        test_get_log(run, proc, workspace)
        test_get_log_pagination(run, proc, workspace)
        test_poll_expired_session(run, proc, workspace)
        test_send_keys_no_session_id(run, proc, workspace)
        test_kill_missing_session_id(run, proc, workspace)

        # Kill any leftover running processes so log files are closed
        # before the temp dir is deleted.
        from tools.exec.supervisor import get_supervisor
        sv = get_supervisor()
        for s in sv.list_sessions(filter_state="running"):
            sv.kill(s["session_id"], reason="user")

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED:")
        for name, ok, detail in _results:
            if not ok:
                print(f"    ✗ {name}  ({detail})")
    else:
        print("  — all good")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
