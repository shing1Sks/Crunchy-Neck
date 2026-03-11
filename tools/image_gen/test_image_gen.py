"""
test_image_gen.py — test suite for the image_gen tool.

Run from the workspace root:
    python -m tools.image_gen.test_image_gen
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
    __package__ = "tools.image_gen"

import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_image(width: int = 512, height: int = 512) -> MagicMock:
    img = MagicMock()
    img.width = width
    img.height = height
    img.save = MagicMock()
    return img


def _make_response(include_image: bool = True, raise_as_image: Exception | None = None):
    response = MagicMock()
    part = MagicMock()
    if include_image:
        part.inline_data = MagicMock()
        if raise_as_image:
            part.as_image.side_effect = raise_as_image
        else:
            part.as_image.return_value = _make_mock_image()
    else:
        part.inline_data = None
    response.parts = [part]
    return response


def _make_genai_stub(response: MagicMock | None = None) -> tuple[MagicMock, dict]:
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    genai_types_mod = types.ModuleType("google.genai.types")

    genai_types_mod.GenerateContentConfig = MagicMock
    genai_types_mod.ImageConfig = MagicMock

    mock_client = MagicMock()
    if response is not None:
        mock_client.models.generate_content.return_value = response

    genai_mod.Client = MagicMock(return_value=mock_client)
    genai_mod.types = genai_types_mod
    google_mod.genai = genai_mod

    modules = {"google": google_mod, "google.genai": genai_mod, "google.genai.types": genai_types_mod}
    return mock_client, modules


# ---------------------------------------------------------------------------
# Inject genai stub before first import so module loads cleanly
# ---------------------------------------------------------------------------

_, _initial_stub = _make_genai_stub()
for k, v in _initial_stub.items():
    sys.modules.setdefault(k, v)

from .image_gen_tool import image_gen_command  # noqa: E402
from .image_gen_types import ImageGenParams    # noqa: E402

PATCH_LOG    = "tools.image_gen.image_gen_tool.log_event"
PATCH_DOTENV = "tools.image_gen.image_gen_tool.load_dotenv"
SESSION = "test-session"
FAKE_KEY = {"GEMINI_API_KEY": "fake-api-key"}
NO_KEY   = {"GEMINI_API_KEY": ""}


def _run(params: ImageGenParams, tmp: str, response=None):
    if response is None:
        response = _make_response()
    mock_client, modules = _make_genai_stub(response)
    with (
        patch.dict(sys.modules, modules),
        patch(PATCH_DOTENV),
        patch.dict(os.environ, FAKE_KEY),
        patch(PATCH_LOG),
    ):
        result = image_gen_command(params, workspace_root=tmp, agent_session_id=SESSION)
    return result, mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_basic_generation() -> None:
    section("Successful image generation")
    with TemporaryDirectory() as tmp:
        r, _ = _run(ImageGenParams(prompt="a cat"), tmp)
        check("status=done", r.status == "done", str(r))
        p = Path(r.path)
        check("path under .agent/images", p.parts[0] == ".agent" and p.parts[1] == "images", r.path)
        check("filename starts img-", p.name.startswith("img-"), p.name)
        check("path ends .png", r.path.endswith(".png"), r.path)
        check("width=512", r.width == 512)
        check("height=512", r.height == 512)
        check("prompt preserved", r.prompt == "a cat")
        check("output dir created", (Path(tmp) / ".agent" / "images").is_dir())


def test_generate_called_with_prompt() -> None:
    section("generate_content called with correct prompt")
    with TemporaryDirectory() as tmp:
        params = ImageGenParams(prompt="a dog", size=256, aspect_ratio="16:9")
        _, mock_client = _run(params, tmp)
        call = mock_client.models.generate_content.call_args
        check("contents=prompt", call.kwargs.get("contents") == "a dog", str(call))


def test_image_save_format() -> None:
    section("img.save called with format=PNG")
    with TemporaryDirectory() as tmp:
        mock_img = _make_mock_image()
        part = MagicMock()
        part.inline_data = MagicMock()
        part.as_image.return_value = mock_img
        resp = MagicMock()
        resp.parts = [part]
        _run(ImageGenParams(prompt="p"), tmp, response=resp)
        mock_img.save.assert_called_once()
        _, kw = mock_img.save.call_args
        check("format=PNG", kw.get("format") == "PNG", str(kw))


def test_not_configured() -> None:
    section("Missing GEMINI_API_KEY -> not_configured")
    with TemporaryDirectory() as tmp:
        _, modules = _make_genai_stub()
        with (
            patch.dict(sys.modules, modules),
            patch(PATCH_DOTENV),
            patch.dict(os.environ, NO_KEY),
            patch(PATCH_LOG),
        ):
            r = image_gen_command(ImageGenParams(prompt="x"), workspace_root=tmp, agent_session_id=SESSION)
        check("status=error", r.status == "error", str(r))
        check("error_code=not_configured", r.error_code == "not_configured", str(r))
        check("detail mentions GEMINI_API_KEY", "GEMINI_API_KEY" in r.detail, r.detail)


def test_api_error() -> None:
    section("API exception -> api_error")
    with TemporaryDirectory() as tmp:
        mock_client, modules = _make_genai_stub()
        mock_client.models.generate_content.side_effect = RuntimeError("API down")
        with (
            patch.dict(sys.modules, modules),
            patch(PATCH_DOTENV),
            patch.dict(os.environ, FAKE_KEY),
            patch(PATCH_LOG),
        ):
            r = image_gen_command(ImageGenParams(prompt="x"), workspace_root=tmp, agent_session_id=SESSION)
        check("status=error", r.status == "error", str(r))
        check("error_code=api_error", r.error_code == "api_error", str(r))
        check("detail contains exception message", "API down" in r.detail, r.detail)


def test_no_image_in_response() -> None:
    section("Response has no image part -> no_image_in_response")
    with TemporaryDirectory() as tmp:
        r, _ = _run(ImageGenParams(prompt="x"), tmp, response=_make_response(include_image=False))
        check("status=error", r.status == "error", str(r))
        check("error_code=no_image_in_response", r.error_code == "no_image_in_response", str(r))


def test_as_image_raises() -> None:
    section("part.as_image() raises -> api_error")
    with TemporaryDirectory() as tmp:
        resp = _make_response(include_image=True, raise_as_image=ValueError("bad data"))
        r, _ = _run(ImageGenParams(prompt="x"), tmp, response=resp)
        check("status=error", r.status == "error", str(r))
        check("error_code=api_error", r.error_code == "api_error", str(r))
        check("detail contains exception message", "bad data" in r.detail, r.detail)


def test_save_failed() -> None:
    section("img.save raises -> save_failed")
    with TemporaryDirectory() as tmp:
        mock_img = _make_mock_image()
        mock_img.save.side_effect = OSError("disk full")
        part = MagicMock()
        part.inline_data = MagicMock()
        part.as_image.return_value = mock_img
        resp = MagicMock()
        resp.parts = [part]
        r, _ = _run(ImageGenParams(prompt="x"), tmp, response=resp)
        check("status=error", r.status == "error", str(r))
        check("error_code=save_failed", r.error_code == "save_failed", str(r))
        check("detail contains exception message", "disk full" in r.detail, r.detail)


def test_audit_done() -> None:
    section("Audit - image_gen.done event logged")
    with TemporaryDirectory() as tmp:
        mock_client, modules = _make_genai_stub(_make_response())
        with (
            patch.dict(sys.modules, modules),
            patch(PATCH_DOTENV),
            patch.dict(os.environ, FAKE_KEY),
            patch(PATCH_LOG) as mock_log,
        ):
            image_gen_command(ImageGenParams(prompt="audit test"), workspace_root=tmp, agent_session_id=SESSION)
        check("log called", mock_log.called)
        check("event=image_gen.done", mock_log.call_args.kwargs.get("event") == "image_gen.done",
              str(mock_log.call_args))


def test_audit_error() -> None:
    section("Audit - image_gen.error event logged on failure")
    with TemporaryDirectory() as tmp:
        _, modules = _make_genai_stub()
        with (
            patch.dict(sys.modules, modules),
            patch(PATCH_DOTENV),
            patch.dict(os.environ, NO_KEY),
            patch(PATCH_LOG) as mock_log,
        ):
            image_gen_command(ImageGenParams(prompt="x"), workspace_root=tmp, agent_session_id=SESSION)
        check("log called", mock_log.called)
        check("event=image_gen.error", mock_log.call_args.kwargs.get("event") == "image_gen.error",
              str(mock_log.call_args))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  image_gen - test suite")
    print("=" * 60)

    test_basic_generation()
    test_generate_called_with_prompt()
    test_image_save_format()
    test_not_configured()
    test_api_error()
    test_no_image_in_response()
    test_as_image_raises()
    test_save_failed()
    test_audit_done()
    test_audit_error()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
