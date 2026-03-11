from __future__ import annotations

import threading
from pathlib import Path

from memory import ChromaUnavailableError, LongTermMemStore

from .audit import log_event
from .remember_types import (
    MemoryHit,
    RememberParams,
    RememberResult,
    RememberResultDeleted,
    RememberResultError,
    RememberResultListed,
    RememberResultQueried,
    RememberResultStored,
)

# Per-chroma_dir store registry — tests use unique temp dirs so each gets a
# fresh, isolated store without cross-contamination between test cases.
_stores: dict[str, LongTermMemStore] = {}
_stores_lock = threading.Lock()


def _get_store(chroma_dir: str) -> LongTermMemStore:
    with _stores_lock:
        if chroma_dir not in _stores:
            _stores[chroma_dir] = LongTermMemStore(chroma_dir)
        return _stores[chroma_dir]


def _chroma_dir(workspace_root: str) -> str:
    return str(Path(workspace_root) / ".agent" / "memory" / "chroma")


def remember_command(
    params: RememberParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> RememberResult:
    store = _get_store(_chroma_dir(workspace_root))

    # ── action: store ─────────────────────────────────────────────────────────
    if params.action == "store":
        if not params.content:
            log_event(
                event="memory.error",
                action="store",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="MISSING_CONTENT",
            )
            return RememberResultError(
                action="store",
                error_code="MISSING_CONTENT",
                error_message="action='store' requires non-empty content.",
            )
        try:
            memory_id, ts = store.store(
                params.content,
                agent_session_id=agent_session_id,
                tags=params.tags,
            )
        except ChromaUnavailableError as exc:
            log_event(
                event="memory.error",
                action="store",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="CHROMA_UNAVAILABLE",
            )
            return RememberResultError(
                action="store",
                error_code="CHROMA_UNAVAILABLE",
                error_message=str(exc),
            )
        except Exception as exc:
            log_event(
                event="memory.error",
                action="store",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="CHROMA_ERROR",
            )
            return RememberResultError(
                action="store",
                error_code="CHROMA_ERROR",
                error_message=str(exc),
            )

        preview = (params.content[:120] + "...") if len(params.content) > 120 else params.content
        log_event(
            event="memory.stored",
            action="store",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            memory_id=memory_id,
            content_preview=preview,
            tags=params.tags,
        )
        return RememberResultStored(
            action="store",
            memory_id=memory_id,
            content_preview=preview,
            tags=params.tags or [],
            timestamp=ts,
        )

    # ── action: query ─────────────────────────────────────────────────────────
    if params.action == "query":
        if not params.query:
            log_event(
                event="memory.error",
                action="query",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="MISSING_QUERY",
            )
            return RememberResultError(
                action="query",
                error_code="MISSING_QUERY",
                error_message="action='query' requires a non-empty query string.",
            )
        n = max(1, min(params.n_results, 50))
        try:
            raw_hits, total = store.query(params.query, n_results=n)
        except ChromaUnavailableError as exc:
            log_event(
                event="memory.error",
                action="query",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="CHROMA_UNAVAILABLE",
            )
            return RememberResultError(
                action="query",
                error_code="CHROMA_UNAVAILABLE",
                error_message=str(exc),
            )
        except Exception as exc:
            log_event(
                event="memory.error",
                action="query",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                error_code="CHROMA_ERROR",
            )
            return RememberResultError(
                action="query",
                error_code="CHROMA_ERROR",
                error_message=str(exc),
            )

        hits = [MemoryHit(**h) for h in raw_hits]
        log_event(
            event="memory.queried",
            action="query",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            query=params.query,
            n_results=n,
            hits_returned=len(hits),
        )
        return RememberResultQueried(
            action="query",
            query=params.query,
            hits=hits,
            total_in_collection=total,
        )

    # ── action: list ──────────────────────────────────────────────────────────
    if params.action == "list":
        try:
            raw_items, total = store.list_all()
        except ChromaUnavailableError as exc:
            return RememberResultError(
                action="list",
                error_code="CHROMA_UNAVAILABLE",
                error_message=str(exc),
            )
        except Exception as exc:
            return RememberResultError(
                action="list",
                error_code="CHROMA_ERROR",
                error_message=str(exc),
            )

        memories = [MemoryHit(**item) for item in raw_items]
        log_event(
            event="memory.listed",
            action="list",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            hits_returned=total,
        )
        return RememberResultListed(action="list", memories=memories, total=total)

    # ── action: delete ────────────────────────────────────────────────────────
    if params.action == "delete":
        if not params.memory_id:
            return RememberResultError(
                action="delete",
                error_code="MISSING_MEMORY_ID",
                error_message="action='delete' requires memory_id.",
            )
        try:
            found = store.delete(params.memory_id)
        except ChromaUnavailableError as exc:
            return RememberResultError(
                action="delete",
                error_code="CHROMA_UNAVAILABLE",
                error_message=str(exc),
            )
        except Exception as exc:
            return RememberResultError(
                action="delete",
                error_code="CHROMA_ERROR",
                error_message=str(exc),
            )

        if not found:
            log_event(
                event="memory.error",
                action="delete",
                agent_session_id=agent_session_id,
                workspace_root=workspace_root,
                memory_id=params.memory_id,
                error_code="MEMORY_NOT_FOUND",
            )
            return RememberResultError(
                action="delete",
                error_code="MEMORY_NOT_FOUND",
                error_message=f"No memory with id={params.memory_id!r}.",
            )
        log_event(
            event="memory.deleted",
            action="delete",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            memory_id=params.memory_id,
        )
        return RememberResultDeleted(action="delete", memory_id=params.memory_id)

    # ── unknown action ────────────────────────────────────────────────────────
    return RememberResultError(
        action=params.action,
        error_code="INVALID_ACTION",
        error_message=f"Unknown action {params.action!r}. Valid: store, query, list, delete.",
    )
