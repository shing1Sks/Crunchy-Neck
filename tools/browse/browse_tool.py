"""browse_tool — thin wrapper that delegates a task to Scout (computer_agent)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .browse_types import BrowseParams, BrowseResult, BrowseResultDone, BrowseResultFailed


def browse_command(
    params: BrowseParams,
    *,
    workspace_root: str,
    agent_session_id: str,
    medium: str = "telegram",
) -> BrowseResult:
    """
    Hand a GUI task off to Scout and return its result.

    Reads OPENAI_API_KEY from the environment or from a .env file at workspace_root.
    Returns BrowseResultFailed immediately if the key is missing.
    """
    load_dotenv(Path(workspace_root) / ".env", override=False)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return BrowseResultFailed(
            reason="OPENAI_API_KEY not set in environment or .env file at workspace root"
        )

    from computer_agent.agent import run
    from computer_agent.models import RunConfig

    config = RunConfig(
        task=params.task,
        mode=params.mode,
        launch_browser=params.launch_browser,
        max_turns=params.max_turns,
        medium=medium,
    )

    result = run(
        config,
        workspace_root=workspace_root,
        agent_session_id=agent_session_id,
        api_key=api_key,
    )

    if result.status == "done":
        return BrowseResultDone(deliverable=result.deliverable)
    return BrowseResultFailed(reason=result.reason)
