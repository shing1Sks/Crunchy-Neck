"""
test_remember.py — test harness for the remember tool.

Run from the workspace root:
    python -m tools.remember.test_remember

Or directly from inside tools/remember/:
    python test_remember.py
"""
from __future__ import annotations

import io
import json
import os
import sys

# Force UTF-8 stdout on Windows (avoids UnicodeEncodeError for non-ASCII check names).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# Allow `python test_remember.py` from inside tools/remember/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.remember"

import tempfile
from pathlib import Path

from .remember_tool import remember_command
from .remember_types import (
    MemoryHit,
    RememberParams,
    RememberResultDeleted,
    RememberResultError,
    RememberResultListed,
    RememberResultQueried,
    RememberResultStored,
)

# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  [{status}] {name}{suffix}", flush=True)


def section(title: str) -> None:
    print(f"\n{'-' * 60}", flush=True)
    print(f"  {title}")
    print(f"{'-' * 60}")


def make_runner(workspace: str):
    def run(action: str, **kwargs):
        params = RememberParams(action=action, **kwargs)
        return remember_command(params, workspace_root=workspace, agent_session_id="test_session")
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> None:
    # Most tests share one workspace; persistence test gets its own.
    with tempfile.TemporaryDirectory(
        prefix="crunchy_remember_test_", ignore_cleanup_errors=True
    ) as workspace:
        run = make_runner(workspace)
        ws = Path(workspace)

        # ── 1. CHROMA_UNAVAILABLE guard ───────────────────────────────────────
        section("1. CHROMA_UNAVAILABLE — chromadb not importable")
        # Temporarily hide chromadb from sys.modules.
        import sys as _sys
        _saved = _sys.modules.get("chromadb")
        _sys.modules["chromadb"] = None  # type: ignore[assignment]
        # Also invalidate any already-cached store for this workspace by using
        # a fresh path that no store has been created for yet.
        with tempfile.TemporaryDirectory(prefix="crunchy_unavail_", ignore_cleanup_errors=True) as ws_unavail:
            r_unavail = remember_command(
                RememberParams(action="store", content="test"),
                workspace_root=ws_unavail,
                agent_session_id="test_session",
            )
        # Restore chromadb
        if _saved is None:
            _sys.modules.pop("chromadb", None)
        else:
            _sys.modules["chromadb"] = _saved
        check("status=error", r_unavail.status == "error")
        check(
            "error_code=CHROMA_UNAVAILABLE",
            isinstance(r_unavail, RememberResultError)
            and r_unavail.error_code == "CHROMA_UNAVAILABLE",
        )

        # ── 2. store smoke test ───────────────────────────────────────────────
        section("2. store — smoke test")
        print("[test] about to call store...", flush=True)
        r = run("store", content="The workspace root is /home/agent", tags=["config", "workspace"])
        print(f"[test] store returned: status={r.status!r}", flush=True)
        _r2_detail = f"got status={r.status!r}, error_code={getattr(r, 'error_code', None)!r}, msg={getattr(r, 'error_message', None)!r}"
        check("status=stored", r.status == "stored", _r2_detail)
        check("memory_id non-empty", isinstance(r, RememberResultStored) and bool(r.memory_id))
        check(
            "content_preview starts with content",
            isinstance(r, RememberResultStored)
            and r.content_preview.startswith("The workspace root"),
        )
        check(
            "timestamp is ISO string",
            isinstance(r, RememberResultStored) and "T" in r.timestamp,
        )
        check(
            "tags round-trip",
            isinstance(r, RememberResultStored) and r.tags == ["config", "workspace"],
        )

        # ── 3. store: MISSING_CONTENT ─────────────────────────────────────────
        section("3. store: MISSING_CONTENT")
        r_none = run("store", content=None)
        check("None content -> error", r_none.status == "error")
        check(
            "error_code=MISSING_CONTENT (None)",
            isinstance(r_none, RememberResultError) and r_none.error_code == "MISSING_CONTENT",
        )
        r_empty = run("store", content="")
        check("empty string content -> error", r_empty.status == "error")
        check(
            "error_code=MISSING_CONTENT (empty)",
            isinstance(r_empty, RememberResultError) and r_empty.error_code == "MISSING_CONTENT",
        )

        # ── 4. query smoke test ───────────────────────────────────────────────
        section("4. query — smoke test")
        # Store 3 semantically distinct memories.
        run("store", content="The user prefers dark mode in VS Code", tags=["user_prefs"])
        run("store", content="The project deadline is March 15 2026", tags=["schedule"])
        run("store", content="The database password is stored in .env", tags=["security"])

        r_q = run("query", query="user interface preferences", n_results=2)
        check("status=queried", r_q.status == "queried")
        check(
            "hits <= n_results",
            isinstance(r_q, RememberResultQueried) and len(r_q.hits) <= 2,
        )
        check(
            "total_in_collection >= 4",  # 1 from section 2 + 3 from this section
            isinstance(r_q, RememberResultQueried) and r_q.total_in_collection >= 4,
        )
        check(
            "hits are MemoryHit",
            isinstance(r_q, RememberResultQueried)
            and all(isinstance(h, MemoryHit) for h in r_q.hits),
        )
        if isinstance(r_q, RememberResultQueried) and r_q.hits:
            top = r_q.hits[0]
            check("hit has memory_id", bool(top.memory_id))
            check("hit has distance (float)", isinstance(top.distance, float))
            check("hit has timestamp", bool(top.timestamp))
            check("hit has session_id", bool(top.session_id))

        # ── 5. query: MISSING_QUERY ───────────────────────────────────────────
        section("5. query: MISSING_QUERY")
        r_nq = run("query", query=None)
        check("None query -> error", r_nq.status == "error")
        check(
            "error_code=MISSING_QUERY (None)",
            isinstance(r_nq, RememberResultError) and r_nq.error_code == "MISSING_QUERY",
        )
        r_eq = run("query", query="")
        check("empty query -> error", r_eq.status == "error")
        check(
            "error_code=MISSING_QUERY (empty)",
            isinstance(r_eq, RememberResultError) and r_eq.error_code == "MISSING_QUERY",
        )

        # ── 6. query: n_results clamping ──────────────────────────────────────
        section("6. query: n_results clamping")
        r_big = run("query", query="memory", n_results=100)
        check(
            "n_results=100 -> no crash, hits <= actual count",
            isinstance(r_big, RememberResultQueried)
            and len(r_big.hits) <= r_big.total_in_collection,
        )
        r_zero = run("query", query="memory", n_results=0)
        check(
            "n_results=0 -> clamped to 1, returns >=1 hit (if collection non-empty)",
            isinstance(r_zero, RememberResultQueried) and len(r_zero.hits) >= 1,
        )

        # ── 7. query: empty collection ────────────────────────────────────────
        section("7. query: empty collection")
        with tempfile.TemporaryDirectory(prefix="crunchy_empty_", ignore_cleanup_errors=True) as ws_empty:
            r_empty_q = remember_command(
                RememberParams(action="query", query="anything"),
                workspace_root=ws_empty,
                agent_session_id="test_session",
            )
        check("status=queried", r_empty_q.status == "queried")
        check(
            "hits=[]",
            isinstance(r_empty_q, RememberResultQueried) and r_empty_q.hits == [],
        )
        check(
            "total_in_collection=0",
            isinstance(r_empty_q, RememberResultQueried) and r_empty_q.total_in_collection == 0,
        )

        # ── 8. list smoke test ────────────────────────────────────────────────
        section("8. list — smoke test")
        r_list = run("list")
        check("status=listed", r_list.status == "listed")
        check(
            "total >= 4",
            isinstance(r_list, RememberResultListed) and r_list.total >= 4,
        )
        check(
            "memories are MemoryHit",
            isinstance(r_list, RememberResultListed)
            and all(isinstance(m, MemoryHit) for m in r_list.memories),
        )
        check(
            "distance=0.0 for all list hits",
            isinstance(r_list, RememberResultListed)
            and all(m.distance == 0.0 for m in r_list.memories),
        )

        # ── 9. list: empty collection ─────────────────────────────────────────
        section("9. list: empty collection")
        with tempfile.TemporaryDirectory(prefix="crunchy_empty2_", ignore_cleanup_errors=True) as ws_empty2:
            r_empty_list = remember_command(
                RememberParams(action="list"),
                workspace_root=ws_empty2,
                agent_session_id="test_session",
            )
        check("status=listed", r_empty_list.status == "listed")
        check(
            "memories=[], total=0",
            isinstance(r_empty_list, RememberResultListed)
            and r_empty_list.memories == []
            and r_empty_list.total == 0,
        )

        # ── 10. delete smoke test ─────────────────────────────────────────────
        section("10. delete — smoke test")
        r_store_del = run("store", content="This memory will be deleted", tags=["temp"])
        _r10_detail = f"store returned status={r_store_del.status!r}, error_code={getattr(r_store_del, 'error_code', None)!r}"
        check("pre-delete store succeeded", isinstance(r_store_del, RememberResultStored), _r10_detail)
        if isinstance(r_store_del, RememberResultStored):
            del_id = r_store_del.memory_id
            r_del = run("delete", memory_id=del_id)
            check("status=deleted", r_del.status == "deleted")
            check(
                "memory_id echoed back",
                isinstance(r_del, RememberResultDeleted) and r_del.memory_id == del_id,
            )
            # Verify it's gone from list.
            r_after = run("list")
            ids_after = [m.memory_id for m in r_after.memories] if isinstance(r_after, RememberResultListed) else []
            check("deleted id not in list", del_id not in ids_after)
        else:
            check("status=deleted", False, "skipped: store failed")
            check("memory_id echoed back", False, "skipped: store failed")
            check("deleted id not in list", False, "skipped: store failed")

        # ── 11. delete: MEMORY_NOT_FOUND ──────────────────────────────────────
        section("11. delete: MEMORY_NOT_FOUND")
        r_missing = run("delete", memory_id="00000000-0000-0000-0000-000000000000")
        check("status=error", r_missing.status == "error")
        check(
            "error_code=MEMORY_NOT_FOUND",
            isinstance(r_missing, RememberResultError) and r_missing.error_code == "MEMORY_NOT_FOUND",
        )

        # ── 12. delete: MISSING_MEMORY_ID ─────────────────────────────────────
        section("12. delete: MISSING_MEMORY_ID")
        r_no_id = run("delete", memory_id=None)
        check("status=error", r_no_id.status == "error")
        check(
            "error_code=MISSING_MEMORY_ID",
            isinstance(r_no_id, RememberResultError) and r_no_id.error_code == "MISSING_MEMORY_ID",
        )

        # ── 14. audit log written ─────────────────────────────────────────────
        section("14. audit log — JSONL written and parseable")
        audit_dir = ws / ".agent" / "audit"
        audit_files = list(audit_dir.glob("memory-*.jsonl")) if audit_dir.exists() else []
        check("audit file exists", len(audit_files) >= 1)
        if audit_files:
            events_found: set[str] = set()
            all_valid_json = True
            all_have_session = True
            for line in audit_files[0].read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    events_found.add(rec.get("event", ""))
                    if "agent_session_id" not in rec:
                        all_have_session = False
                except json.JSONDecodeError:
                    all_valid_json = False
            check("all lines are valid JSON", all_valid_json)
            check("agent_session_id on every record", all_have_session)
            check("memory.stored event present", "memory.stored" in events_found)
            check("memory.queried event present", "memory.queried" in events_found)
            check("memory.deleted event present", "memory.deleted" in events_found)

        # ── 15. tags round-trip ───────────────────────────────────────────────
        section("15. tags round-trip")
        r_tagged = run("store", content="tagged memory test", tags=["topic:A", "topic:B"])
        _r15_detail = f"store returned status={r_tagged.status!r}, error_code={getattr(r_tagged, 'error_code', None)!r}"
        check("tags store succeeded", isinstance(r_tagged, RememberResultStored), _r15_detail)
        if isinstance(r_tagged, RememberResultStored):
            r_list2 = run("list")
            tagged_mem = None
            if isinstance(r_list2, RememberResultListed):
                for m in r_list2.memories:
                    if m.memory_id == r_tagged.memory_id:
                        tagged_mem = m
                        break
            check("memory found in list", tagged_mem is not None)
            check(
                "tags round-trip correctly",
                tagged_mem is not None and tagged_mem.tags == ["topic:A", "topic:B"],
            )
        else:
            check("memory found in list", False, "skipped: store failed")
            check("tags round-trip correctly", False, "skipped: store failed")

        # ── 16. invalid action ────────────────────────────────────────────────
        section("16. invalid action -> INVALID_ACTION")
        r_inv = remember_command(
            RememberParams(action="purge"),  # type: ignore[arg-type]
            workspace_root=workspace,
            agent_session_id="test_session",
        )
        check("status=error", r_inv.status == "error")
        check(
            "error_code=INVALID_ACTION",
            isinstance(r_inv, RememberResultError) and r_inv.error_code == "INVALID_ACTION",
        )

        # ── 17. Unicode content round-trip ────────────────────────────────────
        section("17. Unicode content round-trip")
        unicode_content = "エージェントの記憶テスト 🧠"
        r_uni = run("store", content=unicode_content)
        _r17_detail = f"store returned status={r_uni.status!r}, error_code={getattr(r_uni, 'error_code', None)!r}"
        check("unicode store succeeded", isinstance(r_uni, RememberResultStored), _r17_detail)
        if isinstance(r_uni, RememberResultStored):
            r_list3 = run("list")
            uni_mem = None
            if isinstance(r_list3, RememberResultListed):
                for m in r_list3.memories:
                    if m.memory_id == r_uni.memory_id:
                        uni_mem = m
                        break
            check("unicode memory found in list", uni_mem is not None)
            check(
                "unicode content intact",
                uni_mem is not None and uni_mem.content == unicode_content,
            )
        else:
            check("unicode memory found in list", False, "skipped: store failed")
            check("unicode content intact", False, "skipped: store failed")

    # ── 13. persistence across LongTermMemStore instances ────────────────────
    section("13. persistence — data survives new store instance")
    with tempfile.TemporaryDirectory(
        prefix="crunchy_persist_test_", ignore_cleanup_errors=True
    ) as ws_persist:
        # Store via the tool (which caches a store internally).
        r_p = remember_command(
            RememberParams(action="store", content="persisted fact: sky is blue"),
            workspace_root=ws_persist,
            agent_session_id="persist_session",
        )
        _r13_detail = f"store returned status={r_p.status!r}, error_code={getattr(r_p, 'error_code', None)!r}"
        check("persist store succeeded", isinstance(r_p, RememberResultStored), _r13_detail)
        if isinstance(r_p, RememberResultStored):
            stored_id = r_p.memory_id
            # Create a brand-new LongTermMemStore bypassing the tool's cache.
            from memory.long_term_mem.store import LongTermMemStore

            chroma_path = str(Path(ws_persist) / ".agent" / "memory" / "chroma")
            fresh_store = LongTermMemStore(chroma_path)
            items, total = fresh_store.list_all()
            ids = [item["memory_id"] for item in items]
            check("total >= 1 in fresh store", total >= 1)
            check("stored id found in fresh store", stored_id in ids)
            match = next((i for i in items if i["memory_id"] == stored_id), None)
            check(
                "content intact in fresh store",
                match is not None and match["content"] == "persisted fact: sky is blue",
            )
        else:
            check("total >= 1 in fresh store", False, "skipped: store failed")
            check("stored id found in fresh store", False, "skipped: store failed")
            check("content intact in fresh store", False, "skipped: store failed")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"  Results: {passed} passed, {failed} failed out of {len(_results)} checks")
    print(f"{'=' * 60}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
