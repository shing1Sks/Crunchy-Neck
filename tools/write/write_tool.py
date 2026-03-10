from __future__ import annotations

import os
import uuid

from ..file_safety import resolve_path
from .audit import log_event
from .write_types import (
    WriteParams,
    WriteResult,
    WriteResultDone,
    WriteResultError,
)


def _count_lines(content: str) -> int:
    """Return the number of lines in *content* (same as wc -l + 1 if no trailing newline)."""
    if not content:
        return 0
    count = content.count("\n")
    if not content.endswith("\n"):
        count += 1
    return count


def write_command(
    params: WriteParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> WriteResult:
    # ------------------------------------------------------------------
    # 1. Path safety
    # ------------------------------------------------------------------
    resolved, err = resolve_path(params.path, workspace_root)
    if err:
        log_event(
            event="write.blocked",
            path=params.path,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            blocked_reason=err,
        )
        return WriteResultError(
            path=params.path,
            error_code="BLOCKED_PATH",
            error_message=f"Path is blocked: {params.path}",
        )

    path_str = str(resolved)

    # ------------------------------------------------------------------
    # 2. Encode content upfront (validates encoding + checks size)
    # ------------------------------------------------------------------
    try:
        encoded = params.content.encode(params.encoding)
    except (LookupError, UnicodeEncodeError) as exc:
        return WriteResultError(
            path=path_str,
            error_code="ENCODING_ERROR",
            error_message=f"Cannot encode content with '{params.encoding}': {exc}",
        )

    if len(encoded) > params.max_bytes:
        return WriteResultError(
            path=path_str,
            error_code="SIZE_LIMIT_EXCEEDED",
            error_message=(
                f"Content size {len(encoded)} bytes exceeds max_bytes={params.max_bytes}."
            ),
        )

    # ------------------------------------------------------------------
    # 3. Parent directory
    # ------------------------------------------------------------------
    parent = resolved.parent
    if not parent.exists():
        if params.create_parents:
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return WriteResultError(
                    path=path_str,
                    error_code="PERMISSION_DENIED",
                    error_message=f"Cannot create parent directories: {exc}",
                )
        else:
            return WriteResultError(
                path=path_str,
                error_code="PARENT_NOT_FOUND",
                error_message=f"Parent directory does not exist: {parent}",
            )

    # ------------------------------------------------------------------
    # 4. Overwrite guard
    # ------------------------------------------------------------------
    file_existed = resolved.exists()
    if file_existed and not params.overwrite:
        return WriteResultError(
            path=path_str,
            error_code="FILE_EXISTS",
            error_message=f"File already exists and overwrite=False: {path_str}",
        )

    # ------------------------------------------------------------------
    # 5. Audit start
    # ------------------------------------------------------------------
    log_event(
        event="write.start",
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=params.encoding,
        bytes_written=len(encoded),
        atomic=params.atomic,
    )

    # ------------------------------------------------------------------
    # 6. Write
    # ------------------------------------------------------------------
    if params.atomic:
        tmp = parent / f".~{resolved.name}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            tmp.write_bytes(encoded)
            os.replace(tmp, resolved)
        except PermissionError as exc:
            tmp.unlink(missing_ok=True)
            log_event(
                event="write.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="PERMISSION_DENIED",
            )
            return WriteResultError(
                path=path_str,
                error_code="PERMISSION_DENIED",
                error_message=str(exc),
            )
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            log_event(
                event="write.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="INTERNAL",
            )
            return WriteResultError(
                path=path_str,
                error_code="INTERNAL",
                error_message=str(exc),
            )
    else:
        try:
            resolved.write_bytes(encoded)
        except PermissionError as exc:
            log_event(
                event="write.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="PERMISSION_DENIED",
            )
            return WriteResultError(
                path=path_str,
                error_code="PERMISSION_DENIED",
                error_message=str(exc),
            )
        except OSError as exc:
            log_event(
                event="write.error",
                path=path_str,
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="INTERNAL",
            )
            return WriteResultError(
                path=path_str,
                error_code="INTERNAL",
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # 7. Audit done + return
    # ------------------------------------------------------------------
    lines_written = _count_lines(params.content)

    log_event(
        event="write.done",
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=params.encoding,
        bytes_written=len(encoded),
        lines_written=lines_written,
        atomic=params.atomic,
    )

    return WriteResultDone(
        path=path_str,
        bytes_written=len(encoded),
        lines_written=lines_written,
        created=not file_existed,
        overwritten=file_existed,
        atomic=params.atomic,
    )
