"""image_gen — generate an image from a prompt via Gemini and save as PNG."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .audit import log_event
from .image_gen_types import (
    ImageGenParams,
    ImageGenResult,
    ImageGenResultDone,
    ImageGenResultError,
)

_MODEL = "gemini-3.1-flash-image-preview"


def image_gen_command(
    params: ImageGenParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> ImageGenResult:
    # ── Import google-genai (optional dep — give a clean error if missing) ─────
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        log_event(event="image_gen.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="dependency_missing",
                  detail="google-genai is not installed. Run: pip install google-genai")
        return ImageGenResultError(
            error_code="dependency_missing",
            detail="google-genai is not installed. Run: pip install google-genai",
        )

    # ── Credentials ────────────────────────────────────────────────────────────
    load_dotenv(Path(workspace_root) / ".env", override=False)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        detail = "GEMINI_API_KEY not set. Set it in the environment or in a .env file at the workspace root."
        log_event(event="image_gen.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="not_configured", detail=detail)
        return ImageGenResultError(error_code="not_configured", detail=detail)

    # ── Generate ───────────────────────────────────────────────────────────────
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_MODEL,
            contents=params.prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=genai_types.ImageConfig(
                    aspect_ratio=params.aspect_ratio,
                    image_size=str(params.size),
                ),
            ),
        )
    except Exception as exc:
        log_event(event="image_gen.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="api_error", detail=str(exc))
        return ImageGenResultError(error_code="api_error", detail=str(exc))

    # ── Extract image bytes ────────────────────────────────────────────────────
    raw_bytes: bytes | None = None
    for part in response.parts:
        if part.inline_data is not None:
            data = part.inline_data.data
            if isinstance(data, str):  # guard: base64 str in some SDK versions
                import base64 as _b64
                data = _b64.b64decode(data)
            raw_bytes = data
            break

    if raw_bytes is None:
        detail = "Gemini returned no image in the response"
        log_event(event="image_gen.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="no_image_in_response",
                  detail=detail)
        return ImageGenResultError(error_code="no_image_in_response", detail=detail)

    # ── Save ───────────────────────────────────────────────────────────────────
    out_dir = Path(workspace_root) / ".agent" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"img-{ts}.png"
    out_path = out_dir / filename

    try:
        out_path.write_bytes(raw_bytes)
    except Exception as exc:
        log_event(event="image_gen.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="save_failed", detail=str(exc))
        return ImageGenResultError(error_code="save_failed", detail=str(exc))

    # ── Get dimensions (non-fatal if PIL unavailable) ──────────────────────────
    width, height = 0, 0
    try:
        import io as _io
        from PIL import Image as _PILImage
        with _PILImage.open(_io.BytesIO(raw_bytes)) as pil_img:
            width, height = pil_img.size
    except Exception:
        pass

    rel_path = str(Path(".agent") / "images" / filename)
    log_event(event="image_gen.done", agent_session_id=agent_session_id,
              workspace_root=workspace_root, path=rel_path,
              prompt=params.prompt[:120], width=width, height=height)

    return ImageGenResultDone(
        path=rel_path,
        width=width,
        height=height,
        prompt=params.prompt,
    )
