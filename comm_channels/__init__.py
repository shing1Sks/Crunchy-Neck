"""comm_channels — backend implementation package for user communication.

The tool entry point (TOOL_DEFINITION, ping_command) lives in tools/ping/.
This package provides the medium-specific backends: telegram/ and terminal/.
"""
from __future__ import annotations

from .ping_tool import ping_user
from .ping_types import PingParams

__all__ = ["ping_user", "PingParams"]
