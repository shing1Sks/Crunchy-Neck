"""
tool_dispatcher.py — maps OpenAI tool_call.function.name → implementation.

dispatch() is the single entry point. It always returns a JSON string — even
on error — so the caller can safely insert it as a tool_result message without
branching on success/failure.

The 'medium' param is injected into ping_user / send_user_media calls so the
model doesn't need to pass it explicitly on every call.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any


def _result_to_dict(result: Any) -> dict:
    """Convert a tool result dataclass to a JSON-serialisable dict."""
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return dataclasses.asdict(result)
    return {"raw": str(result)}


def dispatch(
    tool_name: str,
    arguments_json: str,
    *,
    workspace_root: str,
    agent_session_id: str,
    medium: str,
) -> str:
    """
    Parse arguments_json, call the matching tool, return result as JSON string.
    On any error returns {"error": "..."} JSON so the model can decide what to do.
    """
    try:
        args: dict = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid tool arguments JSON: {e}"})

    try:
        result = _call_tool(tool_name, args, workspace_root, agent_session_id, medium)
        return json.dumps(_result_to_dict(result), default=str)
    except Exception as e:  # noqa: BLE001
        return json.dumps({
            "error": f"Tool '{tool_name}' raised {type(e).__name__}: {e}"
        })


def _filter(args: dict, fields: set[str]) -> dict:
    """Return only the keys present in fields (strips unknown model-hallucinated keys)."""
    return {k: v for k, v in args.items() if k in fields}


def _call_tool(
    name: str,
    args: dict,
    workspace_root: str,
    agent_session_id: str,
    medium: str,
) -> Any:
    # ── exec ──────────────────────────────────────────────────────────────────
    if name == "exec":
        from tools import exec_command, ExecParams
        params = ExecParams(**_filter(args, ExecParams.__dataclass_fields__))
        return exec_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── process ───────────────────────────────────────────────────────────────
    elif name == "process":
        from tools import process_command, ProcessParams
        params = ProcessParams(**_filter(args, ProcessParams.__dataclass_fields__))
        return process_command(params)

    # ── read ──────────────────────────────────────────────────────────────────
    elif name == "read":
        from tools import read_command, ReadParams
        params = ReadParams(**_filter(args, ReadParams.__dataclass_fields__))
        return read_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── write ─────────────────────────────────────────────────────────────────
    elif name == "write":
        from tools import write_command, WriteParams
        params = WriteParams(**_filter(args, WriteParams.__dataclass_fields__))
        return write_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── edit ──────────────────────────────────────────────────────────────────
    elif name == "edit":
        from tools import edit_command, EditParams
        params = EditParams(**_filter(args, EditParams.__dataclass_fields__))
        return edit_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── remember ──────────────────────────────────────────────────────────────
    elif name == "remember":
        from tools import remember_command, RememberParams
        params = RememberParams(**_filter(args, RememberParams.__dataclass_fields__))
        return remember_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── ping_user ─────────────────────────────────────────────────────────────
    elif name == "ping_user":
        from tools import ping_command, PingParams
        # Inject session medium if model didn't specify one
        if "medium" not in args:
            args = {**args, "medium": medium}
        params = PingParams(**_filter(args, PingParams.__dataclass_fields__))
        return ping_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── send_user_media ───────────────────────────────────────────────────────
    elif name == "send_user_media":
        from tools import send_media_command, SendMediaParams
        if "medium" not in args:
            args = {**args, "medium": medium}
        params = SendMediaParams(**_filter(args, SendMediaParams.__dataclass_fields__))
        return send_media_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── snapshot ──────────────────────────────────────────────────────────────
    elif name == "snapshot":
        from tools import snapshot_command, SnapshotParams
        params = SnapshotParams(**_filter(args, SnapshotParams.__dataclass_fields__))
        return snapshot_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── tts ───────────────────────────────────────────────────────────────────
    elif name == "tts":
        from tools import tts_command, TtsParams
        params = TtsParams(**_filter(args, TtsParams.__dataclass_fields__))
        return tts_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    # ── image_gen ─────────────────────────────────────────────────────────────
    elif name == "image_gen":
        from tools import image_gen_command, ImageGenParams
        params = ImageGenParams(**_filter(args, ImageGenParams.__dataclass_fields__))
        return image_gen_command(params, workspace_root=workspace_root, agent_session_id=agent_session_id)

    else:
        raise ValueError(f"Unknown tool: {name!r}")
