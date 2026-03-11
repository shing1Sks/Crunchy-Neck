"""
test_snapshot.py — test suite for the snapshot tool.

Run from the workspace root:
    python -m tools.snapshot.test_snapshot
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.snapshot"

import json
import types
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from .snapshot_tool import snapshot_command
from .snapshot_types import SnapshotParams, SnapshotResultDone, SnapshotResultError

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


def _fake_image(width: int = 800, height: int = 600):
    """Return a minimal mock PIL Image."""
    img = MagicMock()
    img.width = width
    img.height = height

    def _save(fp, format=None, **kw):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        if hasattr(fp, "write"):
            fp.write(data)
        else:
            # fp is a Path — write bytes directly so the file exists on disk
            Path(fp).write_bytes(data)
    img.save = MagicMock(side_effect=_save)
    return img


def _pil_modules(fake_img: MagicMock | None = None) -> dict:
    """Build sys.modules patch dict for PIL / PIL.ImageGrab."""
    pil_mod = types.ModuleType("PIL")
    ig_mod = types.ModuleType("PIL.ImageGrab")
    ig_mod.grab = MagicMock(return_value=fake_img or _fake_image())
    pil_mod.ImageGrab = ig_mod
    return {"PIL": pil_mod, "PIL.ImageGrab": ig_mod}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_basic_snapshot() -> None:
    section("Basic snapshot — full screen, PNG")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        fake_img = _fake_image()
        pil = _pil_modules(fake_img)
        with patch.dict(sys.modules, pil):
            params = SnapshotParams()
            r = snapshot_command(params, workspace_root=ws, agent_session_id="test")

        check("status=done", r.status == "done", str(r))
        check("path contains .agent/snapshots", ".agent" in r.path and "snapshot" in r.path, r.path)
        check("width=800", r.width == 800)
        check("height=600", r.height == 600)
        check("format=png", r.format == "png")
        check("base64 present", r.base64 is not None and len(r.base64) > 0)
        check("file saved", Path(ws, r.path).exists(), r.path)


def test_all_screens_flag() -> None:
    section("monitor=0 passes all_screens=True")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        pil = _pil_modules()
        with patch.dict(sys.modules, pil):
            snapshot_command(SnapshotParams(monitor=0), workspace_root=ws, agent_session_id="test")
            call_kwargs = pil["PIL.ImageGrab"].grab.call_args.kwargs
        check("all_screens=True", call_kwargs.get("all_screens") is True, str(call_kwargs))


def test_specific_monitor() -> None:
    section("monitor=1 passes all_screens=False")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        pil = _pil_modules()
        with patch.dict(sys.modules, pil):
            snapshot_command(SnapshotParams(monitor=1), workspace_root=ws, agent_session_id="test")
            call_kwargs = pil["PIL.ImageGrab"].grab.call_args.kwargs
        check("all_screens=False", call_kwargs.get("all_screens") is False, str(call_kwargs))


def test_region_crop() -> None:
    section("region=[10,20,100,80] -> correct bbox")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        pil = _pil_modules(_fake_image(100, 80))
        with patch.dict(sys.modules, pil):
            snapshot_command(SnapshotParams(region=[10, 20, 100, 80]),
                             workspace_root=ws, agent_session_id="test")
            call_kwargs = pil["PIL.ImageGrab"].grab.call_args.kwargs
        check("bbox=(10,20,110,100)", call_kwargs.get("bbox") == (10, 20, 110, 100),
              str(call_kwargs))


def test_invalid_region() -> None:
    section("invalid region (wrong length)")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        with patch.dict(sys.modules, _pil_modules()):
            r = snapshot_command(SnapshotParams(region=[10, 20]),
                                 workspace_root=ws, agent_session_id="test")
        check("status=error", r.status == "error", str(r))
        check("error_code=invalid_region", r.error_code == "invalid_region", str(r))


def test_include_base64_false() -> None:
    section("include_base64=False -> base64 is None")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        with patch.dict(sys.modules, _pil_modules()):
            r = snapshot_command(SnapshotParams(include_base64=False),
                                 workspace_root=ws, agent_session_id="test")
        check("status=done", r.status == "done", str(r))
        check("base64=None", r.base64 is None)


def test_jpeg_format() -> None:
    section("format=jpeg -> .jpg extension")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        with patch.dict(sys.modules, _pil_modules()):
            r = snapshot_command(SnapshotParams(format="jpeg"),
                                 workspace_root=ws, agent_session_id="test")
        check("status=done", r.status == "done", str(r))
        check("path ends .jpg", r.path.endswith(".jpg"), r.path)


def test_capture_failed() -> None:
    section("ImageGrab raises -> capture_failed")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        pil = _pil_modules()
        pil["PIL.ImageGrab"].grab.side_effect = OSError("no display")
        with patch.dict(sys.modules, pil):
            r = snapshot_command(SnapshotParams(), workspace_root=ws, agent_session_id="test")
        check("status=error", r.status == "error", str(r))
        check("error_code=capture_failed", r.error_code == "capture_failed", str(r))


def test_dependency_missing() -> None:
    section("Pillow not installed -> dependency_missing")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        with patch.dict(sys.modules, {"PIL": None, "PIL.ImageGrab": None}):
            r = snapshot_command(SnapshotParams(), workspace_root=ws, agent_session_id="test")
        check("status=error", r.status == "error", str(r))
        check("error_code=dependency_missing", r.error_code == "dependency_missing", str(r))


def test_audit_written() -> None:
    section("Audit — snapshot.done event written")
    with tempfile.TemporaryDirectory(prefix="snap_test_") as ws:
        with patch.dict(sys.modules, _pil_modules()):
            snapshot_command(SnapshotParams(include_base64=False),
                             workspace_root=ws, agent_session_id="test")

        audit_dir = Path(ws) / ".agent" / "audit"
        logs = list(audit_dir.glob("snapshot-*.jsonl"))
        check("audit file created", len(logs) > 0,
              str(list(audit_dir.iterdir()) if audit_dir.exists() else []))
        if logs:
            events = [json.loads(ln)["event"] for ln in logs[0].read_text().splitlines() if ln.strip()]
            check("snapshot.done logged", "snapshot.done" in events, str(events))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  snapshot — test suite")
    print("=" * 60)

    test_basic_snapshot()
    test_all_screens_flag()
    test_specific_monitor()
    test_region_crop()
    test_invalid_region()
    test_include_base64_false()
    test_jpeg_format()
    test_capture_failed()
    test_dependency_missing()
    test_audit_written()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
