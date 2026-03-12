"""Unit tests for browse tool — no live Scout calls."""
from __future__ import annotations

import pytest

from tools.browse.browse_types import BrowseParams, BrowseResultDone, BrowseResultFailed
from tools.browse.browse_tool import browse_command


def test_browse_params_defaults():
    p = BrowseParams(task="go to google.com")
    assert p.mode == "browser"
    assert p.launch_browser is True
    assert p.max_turns == 60


def test_browse_params_custom():
    p = BrowseParams(task="open notepad", mode="desktop", launch_browser=False, max_turns=30)
    assert p.mode == "desktop"
    assert p.launch_browser is False
    assert p.max_turns == 30


def test_browse_fails_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = browse_command(
        BrowseParams(task="test"),
        workspace_root=str(tmp_path),
        agent_session_id="test-sess",
        medium="terminal",
    )
    assert isinstance(result, BrowseResultFailed)
    assert "OPENAI_API_KEY" in result.reason


def test_result_done_fields():
    r = BrowseResultDone(deliverable="Found 5 results")
    assert r.status == "done"
    assert r.deliverable == "Found 5 results"


def test_result_failed_fields():
    r = BrowseResultFailed(reason="Login required")
    assert r.status == "failed"
    assert r.reason == "Login required"
