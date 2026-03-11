"""
test_ping.py -- 24 test scenarios for the ping_user tool.

Run from the workspace root:
    python -m tools.ping.test_ping

Or directly:
    python test_ping.py
"""
from __future__ import annotations

import json
import os
import sys

# Allow `python test_ping.py` from inside tools/ping/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.ping"

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from .ping_tool import ping_command
from comm_channels.ping_types import PingParams, PingResultError, PingResultResponse, PingResultSent
from comm_channels.templates import escape_mdv2
from comm_channels._state import load_state, save_state

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  [{status}] {name}{suffix}")


def section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def run(params: PingParams, workspace: str) -> object:
    return ping_command(params, workspace_root=workspace, agent_session_id="test_session")


# ---------------------------------------------------------------------------
# Fake Telegram HTTP responses
# ---------------------------------------------------------------------------

def _sent_msg(msg_id: int = 101) -> dict:
    return {"ok": True, "result": {"message_id": msg_id, "text": "x"}}


def _update_message(update_id: int, msg_id: int, reply_to_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": msg_id,
            "text": text,
            "reply_to_message": {"message_id": reply_to_id},
        },
    }


def _update_callback(update_id: int, msg_id: int, cb_id: str, data: str) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": cb_id,
            "data": data,
            "message": {"message_id": msg_id},
        },
    }


def _make_http_mock(responses: list[dict]):
    """Return a _call mock that pops responses from the front of *responses*."""
    def _call_mock(token, method, payload, *, http_timeout=30):
        if not responses:
            raise RuntimeError(f"Unexpected _call({method})")
        resp = responses.pop(0)
        if not resp.get("ok"):
            from comm_channels.telegram.client import TelegramAPIError
            raise TelegramAPIError(method, resp.get("description", "error"), resp.get("error_code", 400))
        return resp["result"]
    return _call_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: C901
    with tempfile.TemporaryDirectory(
        prefix="crunchy_ping_test_", ignore_cleanup_errors=True
    ) as workspace:
        ws = Path(workspace)

        # -- 1. query:options without options list -------------------------
        section("1. query:options -- missing options list")
        r = run(PingParams(msg="Choose", type="query:options", medium="terminal"), workspace)
        check("status=error", r.status == "error")
        check("error_code=invalid_params",
              isinstance(r, PingResultError) and r.error_code == "invalid_params")

        # -- 2. Missing TELEGRAM_BOT_TOKEN ---------------------------------
        section("2. Telegram -- missing env vars -> not_configured")
        with patch.dict(os.environ, {}, clear=False):
            for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "TELEGRAM_USER_CHAT_ID"]:
                os.environ.pop(var, None)
            r = run(PingParams(msg="hi", type="chat", medium="telegram"), workspace)
        check("status=error", r.status == "error")
        check("error_code=not_configured",
              isinstance(r, PingResultError) and r.error_code == "not_configured")

        # -- 3. Terminal -- update with title -------------------------------
        section("3. Terminal -- update with title")
        import io
        with patch("builtins.print") as mock_print:
            r = run(PingParams(msg="All good", type="update", medium="terminal", title="Status"), workspace)
        check("status=sent", r.status == "sent")
        check("message_id=None", isinstance(r, PingResultSent) and r.message_id is None)
        printed = " ".join(str(c) for call in mock_print.call_args_list for c in call.args)
        check("title in output", "Status" in printed)
        check("UPDATE tag", "[UPDATE]" in printed)

        # -- 4. Terminal -- update without title ----------------------------
        section("4. Terminal -- update without title")
        with patch("builtins.print") as mock_print:
            r = run(PingParams(msg="Running...", type="update", medium="terminal"), workspace)
        check("status=sent", r.status == "sent")
        printed = " ".join(str(c) for call in mock_print.call_args_list for c in call.args)
        check("[UPDATE] tag present", "[UPDATE]" in printed)
        check("body in output", "Running..." in printed)

        # -- 5. Terminal -- chat --------------------------------------------
        section("5. Terminal -- chat")
        with patch("builtins.print") as mock_print:
            r = run(PingParams(msg="Hello user", type="chat", medium="terminal"), workspace)
        check("status=sent", r.status == "sent")
        printed = " ".join(str(c) for call in mock_print.call_args_list for c in call.args)
        check("[AGENT] prefix", "[AGENT]" in printed)
        check("msg in output", "Hello user" in printed)

        # -- 6. Terminal -- query:msg ---------------------------------------
        section("6. Terminal -- query:msg (mocked input)")
        with patch("builtins.input", return_value="  my answer  "):
            r = run(PingParams(msg="What is 2+2?", type="query:msg", medium="terminal"), workspace)
        check("status=response", r.status == "response")
        check("response stripped",
              isinstance(r, PingResultResponse) and r.response == "my answer")

        # -- 7. Terminal -- query:options valid choice ----------------------
        section("7. Terminal -- query:options valid choice")
        with patch("builtins.input", return_value="2"):
            r = run(PingParams(
                msg="Pick one", type="query:options", medium="terminal",
                options=["Alpha", "Beta", "Gamma"]
            ), workspace)
        check("status=response", r.status == "response")
        check("response=Beta",
              isinstance(r, PingResultResponse) and r.response == "Beta")

        # -- 8. Terminal -- query:options out of range ----------------------
        section("8. Terminal -- query:options out of range")
        with patch("builtins.input", return_value="99"):
            r = run(PingParams(
                msg="Pick one", type="query:options", medium="terminal",
                options=["A", "B"]
            ), workspace)
        check("status=error", r.status == "error")
        check("error_code=medium_error",
              isinstance(r, PingResultError) and r.error_code == "medium_error")

        # -- 9. Terminal -- query:options non-numeric -----------------------
        section("9. Terminal -- query:options non-numeric input")
        with patch("builtins.input", return_value="banana"):
            r = run(PingParams(
                msg="Pick one", type="query:options", medium="terminal",
                options=["A", "B"]
            ), workspace)
        check("status=error", r.status == "error")
        check("error_code=medium_error",
              isinstance(r, PingResultError) and r.error_code == "medium_error")

        # -- 10. Terminal -- query:msg stdin closed -------------------------
        section("10. Terminal -- query:msg stdin closed (EOFError)")
        with patch("builtins.input", side_effect=EOFError):
            r = run(PingParams(msg="Question?", type="query:msg", medium="terminal"), workspace)
        check("status=error", r.status == "error")
        check("error_code=medium_error",
              isinstance(r, PingResultError) and r.error_code == "medium_error")

        # -- 11. Telegram -- send_update no prior state ---------------------
        section("11. Telegram -- send_update (no prior state -> sendMessage)")
        _tg_env = {
            "TELEGRAM_BOT_TOKEN": "tok",
            "TELEGRAM_CHAT_ID": "chat123",
        }
        responses = [_sent_msg(200)]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Boot", type="update", medium="telegram", title="Agent"), workspace)
        check("status=sent", r.status == "sent")
        check("message_id=200", isinstance(r, PingResultSent) and r.message_id == 200)
        state = load_state(workspace)
        check("state saved", state.get("last_update_message_id") == 200)

        # -- 12. Telegram -- send_update edit succeeds ----------------------
        section("12. Telegram -- send_update edit_last_update=True (edit succeeds)")
        save_state(workspace, {"last_update_message_id": 200})
        edit_resp = {"ok": True, "result": {"message_id": 200, "text": "edited"}}
        responses = [edit_resp]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Update 2", type="update", medium="telegram"), workspace)
        check("status=sent", r.status == "sent")
        check("same message_id (edited in place)",
              isinstance(r, PingResultSent) and r.message_id == 200)

        # -- 13. Telegram -- "message is not modified" treated as success ---
        section("13. Telegram -- edit returns 'not modified' -> success")
        save_state(workspace, {"last_update_message_id": 200})
        not_modified = {"ok": False, "error_code": 400, "description": "Bad Request: message is not modified"}
        responses_nm = [not_modified]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses_nm)):
                r = run(PingParams(msg="Same", type="update", medium="telegram"), workspace)
        check("status=sent", r.status == "sent")
        check("message_id=200", isinstance(r, PingResultSent) and r.message_id == 200)

        # -- 14. Telegram -- edit fails -> fallback sendMessage --------------
        section("14. Telegram -- edit fails -> fallback sendMessage")
        save_state(workspace, {"last_update_message_id": 200})
        edit_fail = {"ok": False, "error_code": 400, "description": "message to edit not found"}
        new_msg = _sent_msg(300)
        responses_fb = [edit_fail, new_msg]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses_fb)):
                r = run(PingParams(msg="Retry", type="update", medium="telegram"), workspace)
        check("status=sent", r.status == "sent")
        check("new message_id=300", isinstance(r, PingResultSent) and r.message_id == 300)
        check("state updated to 300", load_state(workspace).get("last_update_message_id") == 300)

        # -- 15. Telegram -- update edit_last_update=False ------------------
        section("15. Telegram -- send_update edit_last_update=False")
        save_state(workspace, {"last_update_message_id": 300})
        responses = [_sent_msg(400)]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Force new", type="update", medium="telegram",
                                   edit_last_update=False), workspace)
        check("status=sent", r.status == "sent")
        check("new message_id=400", isinstance(r, PingResultSent) and r.message_id == 400)

        # -- 16. Telegram -- chat success -----------------------------------
        section("16. Telegram -- chat success")
        responses = [_sent_msg(500)]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Hello!", type="chat", medium="telegram"), workspace)
        check("status=sent", r.status == "sent")
        check("message_id=500", isinstance(r, PingResultSent) and r.message_id == 500)

        # -- 17. Telegram -- chat send_failed ------------------------------
        section("17. Telegram -- chat send_failed")
        fail_resp = {"ok": False, "error_code": 403, "description": "Forbidden"}
        responses = [fail_resp]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Hello!", type="chat", medium="telegram"), workspace)
        check("status=error", r.status == "error")
        check("error_code=send_failed",
              isinstance(r, PingResultError) and r.error_code == "send_failed")

        # -- 18. Telegram -- query:msg reply arrives ------------------------
        section("18. Telegram -- query:msg reply arrives immediately")
        send_resp = _sent_msg(600)
        updates_resp = {
            "ok": True,
            "result": [_update_message(1, 601, 600, "User reply text")],
        }
        responses = [send_resp, updates_resp]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(msg="Name?", type="query:msg", medium="telegram", timeout=30), workspace)
        check("status=response", r.status == "response")
        check("response text",
              isinstance(r, PingResultResponse) and r.response == "User reply text")

        # -- 19. Telegram -- query:msg timeout ------------------------------
        section("19. Telegram -- query:msg timeout")
        send_resp = _sent_msg(700)
        empty_updates = {"ok": True, "result": []}
        responses = [send_resp] + [empty_updates] * 50
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                # Use a tiny timeout so the test doesn't actually wait
                with patch("time.monotonic", side_effect=[0, 0, 0, 100]):
                    r = run(PingParams(msg="Name?", type="query:msg", medium="telegram", timeout=1), workspace)
        check("status=error", r.status == "error")
        check("error_code=timeout",
              isinstance(r, PingResultError) and r.error_code == "timeout")

        # -- 20. Telegram -- query:options callback arrives -----------------
        section("20. Telegram -- query:options callback arrives immediately")
        send_resp = _sent_msg(800)
        cb_updates = {
            "ok": True,
            "result": [_update_callback(2, 800, "cb_abc", "Accept")],
        }
        answer_resp = {"ok": True, "result": True}
        responses = [send_resp, cb_updates, answer_resp]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                r = run(PingParams(
                    msg="Proceed?", type="query:options", medium="telegram",
                    options=["Accept", "Reject"], timeout=30
                ), workspace)
        check("status=response", r.status == "response")
        check("response=Accept",
              isinstance(r, PingResultResponse) and r.response == "Accept")

        # -- 21. Telegram -- query:options timeout --------------------------
        section("21. Telegram -- query:options timeout")
        send_resp = _sent_msg(900)
        empty_updates = {"ok": True, "result": []}
        responses = [send_resp] + [empty_updates] * 50
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                with patch("time.monotonic", side_effect=[0, 0, 0, 100]):
                    r = run(PingParams(
                        msg="Choose", type="query:options", medium="telegram",
                        options=["Yes", "No"], timeout=1
                    ), workspace)
        check("status=error", r.status == "error")
        check("error_code=timeout",
              isinstance(r, PingResultError) and r.error_code == "timeout")

        # -- 22. State file -- corrupt JSON recovery ------------------------
        section("22. State file -- corrupt JSON recovery")
        state_path = ws / ".agent" / "comm" / "telegram_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{ not valid json", encoding="utf-8")
        recovered = load_state(workspace)
        check("corrupt -> returns {}", recovered == {})

        # -- 23. Audit file created after successful send -------------------
        section("23. Audit file created after successful send")
        audit_dir = ws / ".agent" / "audit"
        responses = [_sent_msg(1000)]
        with patch.dict(os.environ, _tg_env):
            with patch("comm_channels.telegram.client._call", side_effect=_make_http_mock(responses)):
                run(PingParams(msg="Audited", type="chat", medium="telegram"), workspace)
        audit_files = list(audit_dir.glob("ping-*.jsonl")) if audit_dir.exists() else []
        check("audit file exists", len(audit_files) > 0)
        if audit_files:
            events = [
                json.loads(ln)["event"]
                for ln in audit_files[0].read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            check("ping.done event present", "ping.done" in events)

        # -- 24. escape_mdv2 -- all special chars escaped -------------------
        section("24. escape_mdv2 -- special characters")
        raw = r"hello_world. (test) [link] +bonus ~tilde `code` >quote #hash !bang -dash =eq |pipe {brace}"
        escaped = escape_mdv2(raw)
        check("backslash before underscore", r"\_" in escaped)
        check("backslash before dot", r"\." in escaped)
        check("backslash before open-paren", r"\(" in escaped)
        check("backslash before close-paren", r"\)" in escaped)
        check("backslash before plus", r"\+" in escaped)
        check("plain letters unchanged", "hello" in escaped)

    # -- Summary ---------------------------------------------------------------
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"  Results: {passed} passed, {failed} failed out of {len(_results)} checks")
    print(f"{'=' * 60}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
