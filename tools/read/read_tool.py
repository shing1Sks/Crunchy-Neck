from __future__ import annotations

import base64
import os

from ..file_safety import is_binary_content, resolve_path
from .audit import log_event
from .read_types import (
    ReadParams,
    ReadResult,
    ReadResultDone,
    ReadResultError,
)


def read_command(
    params: ReadParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> ReadResult:
    # ------------------------------------------------------------------
    # 1. Path safety
    # ------------------------------------------------------------------
    resolved, err = resolve_path(params.path, workspace_root)
    if err:
        log_event(
            event="read.blocked",
            path=params.path,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            blocked_reason=err,
        )
        return ReadResultError(
            path=params.path,
            error_code="BLOCKED_PATH",
            error_message=f"Path is blocked: {params.path}",
        )

    path_str = str(resolved)

    # ------------------------------------------------------------------
    # 2. Basic checks (directory / existence / permission)
    # ------------------------------------------------------------------
    if resolved.is_dir():
        return ReadResultError(
            path=path_str,
            error_code="IS_DIRECTORY",
            error_message=f"Path is a directory, not a file: {path_str}",
        )

    if not resolved.exists():
        return ReadResultError(
            path=path_str,
            error_code="NOT_FOUND",
            error_message=f"File not found: {path_str}",
        )

    if not os.access(resolved, os.R_OK):
        return ReadResultError(
            path=path_str,
            error_code="PERMISSION_DENIED",
            error_message=f"Permission denied: {path_str}",
        )

    # ------------------------------------------------------------------
    # 3. Audit start
    # ------------------------------------------------------------------
    log_event(
        event="read.start",
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=params.encoding,
    )

    # ------------------------------------------------------------------
    # 4. Read raw bytes (honour max_bytes)
    # ------------------------------------------------------------------
    try:
        file_size = resolved.stat().st_size
        truncated = False
        truncation_note: str | None = None

        with resolved.open("rb") as fh:
            raw = fh.read(params.max_bytes + 1)

        if len(raw) > params.max_bytes:
            raw = raw[: params.max_bytes]
            truncated = True
            truncation_note = (
                f"File size {file_size} bytes exceeds max_bytes={params.max_bytes}. "
                f"Only the first {params.max_bytes} bytes are returned. "
                "Use start_line + num_lines for pagination."
            )

    except PermissionError:
        log_event(
            event="read.error",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            error_code="PERMISSION_DENIED",
        )
        return ReadResultError(
            path=path_str,
            error_code="PERMISSION_DENIED",
            error_message=f"Permission denied while opening: {path_str}",
        )
    except OSError as exc:
        log_event(
            event="read.error",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            error_code="INTERNAL",
        )
        return ReadResultError(
            path=path_str,
            error_code="INTERNAL",
            error_message=str(exc),
        )

    # ------------------------------------------------------------------
    # 5. Binary detection
    # ------------------------------------------------------------------
    if is_binary_content(raw):
        if params.binary == "error":
            log_event(
                event="read.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="BINARY_FILE",
            )
            return ReadResultError(
                path=path_str,
                error_code="BINARY_FILE",
                error_message=(
                    f"File appears to be binary: {path_str}. "
                    "Set binary='base64' to get base64-encoded content, "
                    "or binary='skip' to return empty content."
                ),
            )
        if params.binary == "base64":
            content = base64.b64encode(raw).decode("ascii")
            log_event(
                event="read.done",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                encoding="base64",
                size_bytes=len(raw),
            )
            return ReadResultDone(
                path=path_str,
                content=content,
                encoding="base64",
                size_bytes=len(raw),
                total_lines=0,
                lines_returned=0,
                truncated=truncated,
                truncation_note=truncation_note,
            )
        # binary == "skip"
        log_event(
            event="read.done",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            encoding=params.encoding,
            size_bytes=len(raw),
        )
        return ReadResultDone(
            path=path_str,
            content="",
            encoding=params.encoding,
            size_bytes=len(raw),
            total_lines=0,
            lines_returned=0,
            truncated=True,
            truncation_note="Binary file skipped (binary='skip').",
        )

    # ------------------------------------------------------------------
    # 6. Decode
    # ------------------------------------------------------------------
    text: str
    used_encoding = params.encoding
    try:
        text = raw.decode(params.encoding)
    except LookupError:
        # Invalid encoding name — no fallback possible.
        log_event(
            event="read.error",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            error_code="ENCODING_ERROR",
        )
        return ReadResultError(
            path=path_str,
            error_code="ENCODING_ERROR",
            error_message=f"Unknown encoding '{params.encoding}': {path_str}",
        )
    except UnicodeDecodeError:
        # Encoding is valid but the bytes don't conform — try latin-1 as fallback.
        if params.encoding.lower() not in ("latin-1", "latin1", "iso-8859-1", "iso8859-1"):
            try:
                text = raw.decode("latin-1")
                used_encoding = "latin-1"
            except Exception:
                log_event(
                    event="read.error",
                    path=path_str,
                    agent_session_id=agent_session_id,
                    workspace_root=workspace_root,
                    error_code="ENCODING_ERROR",
                )
                return ReadResultError(
                    path=path_str,
                    error_code="ENCODING_ERROR",
                    error_message=(
                        f"Cannot decode file with encoding '{params.encoding}' "
                        f"or fallback 'latin-1': {path_str}"
                    ),
                )
        else:
            log_event(
                event="read.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="ENCODING_ERROR",
            )
            return ReadResultError(
                path=path_str,
                error_code="ENCODING_ERROR",
                error_message=(
                    f"Cannot decode file with encoding '{params.encoding}': {path_str}"
                ),
            )

    # ------------------------------------------------------------------
    # 7. Line slicing (pagination)
    # ------------------------------------------------------------------
    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    start = max(0, params.start_line)
    if params.num_lines is not None:
        sliced = lines[start : start + params.num_lines]
    else:
        sliced = lines[start:]

    content = "".join(sliced)
    lines_returned = len(sliced)

    # ------------------------------------------------------------------
    # 8. Audit done + return
    # ------------------------------------------------------------------
    log_event(
        event="read.done",
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=used_encoding,
        size_bytes=len(raw),
        lines_returned=lines_returned,
        truncated=truncated or None,
    )

    return ReadResultDone(
        path=path_str,
        content=content,
        encoding=used_encoding,
        size_bytes=len(raw),
        total_lines=total_lines,
        lines_returned=lines_returned,
        truncated=truncated,
        truncation_note=truncation_note,
    )
