"""snapshot — capture a desktop screenshot and save it to .agent/snapshots/."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from .audit import log_event
from .snapshot_types import (
    SnapshotParams,
    SnapshotResult,
    SnapshotResultDone,
    SnapshotResultError,
)


def snapshot_command(
    params: SnapshotParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> SnapshotResult:
    # ── Import Pillow (optional dep — give a clean error if missing) ───────────
    try:
        from PIL import ImageGrab
    except ImportError:
        _audit(event="snapshot.error", agent_session_id=agent_session_id,
               workspace_root=workspace_root, error_code="dependency_missing",
               detail="Pillow is not installed. Run: pip install Pillow")
        return SnapshotResultError(
            error_code="dependency_missing",
            detail="Pillow is not installed. Run: pip install Pillow",
        )

    # ── Build bounding box from x1/y1/x2/y2 ──────────────────────────────────
    bbox: tuple[int, int, int, int] | None = None
    if all(v is not None for v in (params.x1, params.y1, params.x2, params.y2)):
        bbox = (int(params.x1), int(params.y1), int(params.x2), int(params.y2))

    # ── Capture ────────────────────────────────────────────────────────────────
    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=(params.monitor == 0))
    except Exception as exc:
        _audit(event="snapshot.error", agent_session_id=agent_session_id,
               workspace_root=workspace_root, error_code="capture_failed", detail=str(exc))
        return SnapshotResultError(error_code="capture_failed", detail=str(exc))

    # ── Save to .agent/snapshots/ ──────────────────────────────────────────────
    out_dir = Path(workspace_root) / ".agent" / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = "jpg" if params.format == "jpeg" else "png"
    if params.filename:
        filename = f"{Path(params.filename).stem}.{ext}"
    else:
        filename = f"snapshot-{ts}.{ext}"
    abs_path = out_dir / filename

    try:
        img.save(abs_path, format=params.format.upper())
    except Exception as exc:
        _audit(event="snapshot.error", agent_session_id=agent_session_id,
               workspace_root=workspace_root, error_code="save_failed", detail=str(exc))
        return SnapshotResultError(error_code="save_failed", detail=str(exc))

    # ── Optionally encode to base64 ────────────────────────────────────────────
    b64: str | None = None
    if params.include_base64:
        buf = io.BytesIO()
        img.save(buf, format=params.format.upper())
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    rel_path = str(Path(".agent") / "snapshots" / filename)
    _audit(event="snapshot.done", agent_session_id=agent_session_id,
           workspace_root=workspace_root, path=rel_path,
           width=img.width, height=img.height, format=params.format)

    return SnapshotResultDone(
        path=rel_path,
        width=img.width,
        height=img.height,
        format=params.format,
        base64=b64,
    )


def _audit(*, event: str, agent_session_id: str, workspace_root: str, **kw: object) -> None:
    log_event(event=event, agent_session_id=agent_session_id,
              workspace_root=workspace_root, **kw)
