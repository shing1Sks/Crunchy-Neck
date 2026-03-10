from __future__ import annotations

import re
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared audit lock — all file-op tools (read/write/edit) import this so they
# coordinate writes to the same daily JSONL file without races.
# ---------------------------------------------------------------------------
_file_ops_audit_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Sensitive-file blocklist
# ---------------------------------------------------------------------------
_SENSITIVE: list[re.Pattern[str]] = [
    re.compile(r"(^|[/\\])\.env($|[/\\.])"),          # .env, .env.local, .env.production
    re.compile(r"(^|[/\\])credentials\.json$", re.I),
    re.compile(r"(^|[/\\])id_(rsa|dsa|ecdsa|ed25519)$", re.I),  # SSH private keys
    re.compile(r"(^|[/\\])[^/\\]+\.(pem|key)$", re.I),          # certs / generic keys
    re.compile(r"(^|[/\\])\.ssh[/\\]", re.I),
    re.compile(r"(^|[/\\])\.git[/\\]config$", re.I),             # git credentials
]


def _matches_sensitive(path_str: str) -> bool:
    # Normalise to forward slashes for uniform matching, then test both forms.
    normalised = path_str.replace("\\", "/")
    for pat in _SENSITIVE:
        if pat.search(normalised) or pat.search(path_str):
            return True
    return False


def resolve_path(
    path: str,
    workspace_root: str,
) -> tuple[Path, str | None]:
    """
    Resolve *path* against *workspace_root* and validate it.

    Returns (resolved_absolute_path, None) on success, or
    (Path(path), error_code) on failure where error_code is "BLOCKED_PATH".

    Checks performed (in order):
    1. Resolve symlinks; ensure the result stays inside workspace_root.
    2. Sensitive-file blocklist.
    """
    workspace = Path(workspace_root).resolve()

    # Build candidate path.
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace / candidate

    # Resolve symlinks.  On Windows, resolve() on a non-existent path still
    # normalises .. components without dereferencing symlinks — that is fine
    # for our containment check.
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute()

    # Containment check.
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return (resolved, "BLOCKED_PATH")

    # Sensitive-file check against the resolved path string.
    if _matches_sensitive(str(resolved)):
        return (resolved, "BLOCKED_PATH")

    return (resolved, None)


# ---------------------------------------------------------------------------
# Binary-content detection
# ---------------------------------------------------------------------------

def is_binary_content(data: bytes, sample_size: int = 8192) -> bool:
    """
    Return True if *data* looks like binary content.

    Heuristic: any null byte in the first *sample_size* bytes → binary.
    This matches git's own binary detection logic.
    """
    sample = data[:sample_size]
    return b"\x00" in sample
