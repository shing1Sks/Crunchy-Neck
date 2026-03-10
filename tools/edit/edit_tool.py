from __future__ import annotations

import difflib
import os
import uuid

from ..file_safety import resolve_path
from .audit import log_event
from .edit_types import (
    EditParams,
    EditResult,
    EditResultDone,
    EditResultError,
)


def _compute_diff(original: str, updated: str, path: str) -> tuple[str, int, int]:
    """
    Return (unified_diff_str, lines_added, lines_removed).
    """
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    diff_iter = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    diff_lines = list(diff_iter)
    diff_str = "\n".join(diff_lines)
    lines_added = sum(
        1 for l in diff_lines if l.startswith("+") and not l.startswith("+++")
    )
    lines_removed = sum(
        1 for l in diff_lines if l.startswith("-") and not l.startswith("---")
    )
    return diff_str, lines_added, lines_removed


def edit_command(
    params: EditParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> EditResult:
    # ------------------------------------------------------------------
    # 1. Path safety
    # ------------------------------------------------------------------
    resolved, err = resolve_path(params.path, workspace_root)
    if err:
        log_event(
            event="edit.blocked",
            path=params.path,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            blocked_reason=err,
        )
        return EditResultError(
            path=params.path,
            error_code="BLOCKED_PATH",
            error_message=f"Path is blocked: {params.path}",
        )

    path_str = str(resolved)

    # ------------------------------------------------------------------
    # 2. Basic checks
    # ------------------------------------------------------------------
    if resolved.is_dir():
        return EditResultError(
            path=path_str,
            error_code="IS_DIRECTORY",
            error_message=f"Path is a directory, not a file: {path_str}",
        )

    if not resolved.exists():
        return EditResultError(
            path=path_str,
            error_code="NOT_FOUND",
            error_message=f"File not found: {path_str}",
        )

    if not os.access(resolved, os.R_OK | os.W_OK):
        return EditResultError(
            path=path_str,
            error_code="PERMISSION_DENIED",
            error_message=f"Read/write permission denied: {path_str}",
        )

    # ------------------------------------------------------------------
    # 3. Read current content
    # ------------------------------------------------------------------
    try:
        raw = resolved.read_bytes()
    except PermissionError as exc:
        return EditResultError(
            path=path_str,
            error_code="PERMISSION_DENIED",
            error_message=str(exc),
        )
    except OSError as exc:
        return EditResultError(
            path=path_str,
            error_code="INTERNAL",
            error_message=str(exc),
        )

    try:
        original_text = raw.decode(params.encoding)
    except LookupError:
        return EditResultError(
            path=path_str,
            error_code="ENCODING_ERROR",
            error_message=f"Unknown encoding '{params.encoding}'",
        )
    except UnicodeDecodeError:
        return EditResultError(
            path=path_str,
            error_code="ENCODING_ERROR",
            error_message=f"Cannot decode file with encoding '{params.encoding}': {path_str}",
        )

    # ------------------------------------------------------------------
    # 4. Find and validate occurrences
    # ------------------------------------------------------------------
    count = original_text.count(params.old)

    if count == 0:
        log_event(
            event="edit.error",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            error_code="OLD_NOT_FOUND",
        )
        return EditResultError(
            path=path_str,
            error_code="OLD_NOT_FOUND",
            error_message=(
                f"String not found in {path_str}. "
                "Ensure exact match including whitespace and newlines."
            ),
        )

    if count > 1 and not params.allow_multiple:
        log_event(
            event="edit.error",
            path=path_str,
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            error_code="OLD_AMBIGUOUS",
        )
        return EditResultError(
            path=path_str,
            error_code="OLD_AMBIGUOUS",
            error_message=(
                f"String found {count} times in {path_str}. "
                "Set allow_multiple=True to replace all occurrences."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Perform replacement + compute diff
    # ------------------------------------------------------------------
    new_text = original_text.replace(params.old, params.new)
    diff_preview, lines_added, lines_removed = _compute_diff(
        original_text, new_text, params.path
    )

    # ------------------------------------------------------------------
    # 6. Audit start
    # ------------------------------------------------------------------
    log_event(
        event="edit.start",
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=params.encoding,
        dry_run=params.dry_run or None,
    )

    # ------------------------------------------------------------------
    # 7. Write (unless dry_run)
    # ------------------------------------------------------------------
    if not params.dry_run:
        try:
            encoded = new_text.encode(params.encoding)
        except (LookupError, UnicodeEncodeError) as exc:
            return EditResultError(
                path=path_str,
                error_code="ENCODING_ERROR",
                error_message=f"Cannot re-encode edited content: {exc}",
            )

        if params.atomic:
            tmp = resolved.parent / f".~{resolved.name}.{uuid.uuid4().hex[:8]}.tmp"
            try:
                tmp.write_bytes(encoded)
                os.replace(tmp, resolved)
            except PermissionError as exc:
                tmp.unlink(missing_ok=True)
                log_event(
                    event="edit.error",
                    path=path_str,
                    agent_session_id=agent_session_id,
                    workspace_root=workspace_root,
                    error_code="PERMISSION_DENIED",
                )
                return EditResultError(
                    path=path_str,
                    error_code="PERMISSION_DENIED",
                    error_message=str(exc),
                )
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                log_event(
                    event="edit.error",
                    path=path_str,
                    agent_session_id=agent_session_id,
                    workspace_root=workspace_root,
                    error_code="INTERNAL",
                )
                return EditResultError(
                    path=path_str,
                    error_code="INTERNAL",
                    error_message=str(exc),
                )
        else:
            try:
                resolved.write_bytes(encoded)
            except PermissionError as exc:
                log_event(
                    event="edit.error",
                    path=path_str,
                    agent_session_id=agent_session_id,
                    workspace_root=workspace_root,
                    error_code="PERMISSION_DENIED",
                )
                return EditResultError(
                    path=path_str,
                    error_code="PERMISSION_DENIED",
                    error_message=str(exc),
                )

    # ------------------------------------------------------------------
    # 8. Audit done
    # ------------------------------------------------------------------
    audit_event = "edit.dry_run" if params.dry_run else "edit.done"
    log_event(
        event=audit_event,
        path=path_str,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        encoding=params.encoding,
        replacements_made=count,
        lines_added=lines_added,
        lines_removed=lines_removed,
        dry_run=params.dry_run or None,
    )

    return EditResultDone(
        path=path_str,
        replacements_made=count,
        lines_added=lines_added,
        lines_removed=lines_removed,
        dry_run=params.dry_run,
        diff_preview=diff_preview or None,
    )
