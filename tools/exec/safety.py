"""Safety layer for exec tool.

Three concerns handled here:
1. Intent validation  — is the intent field meaningful?
2. Command blocklist  — hard-blocked patterns (no override)
3. Env sanitization   — protect critical keys; redact secrets in audit log
"""
from __future__ import annotations

import re

# ─── Intent validation ────────────────────────────────────────────────────────

INTENT_MIN_LEN = 10

_GENERIC_INTENTS: set[str] = {
    "run command", "execute", "run this", "bash command",
    "shell command", "do it", "run script", "run", "exec",
    "command", "test", "run it",
}


def validate_intent(intent: str, command: str) -> str | None:
    """Return an error_code string if intent fails, or None if valid."""
    stripped = intent.strip()

    if len(stripped) < INTENT_MIN_LEN:
        return "INTENT_MISSING"

    if stripped.lower() in _GENERIC_INTENTS:
        return "INTENT_GENERIC"

    if stripped.lower() == command.strip().lower():
        return "INTENT_GENERIC"

    # If command has 'rm ', intent must mention deletion/cleanup.
    if re.search(r"\brm\s+", command) and not re.search(
        r"(delet|remov|clean|purge|wipe|trash|clear)", stripped, re.I
    ):
        return "INTENT_GENERIC"

    return None


# ─── Command blocklist ────────────────────────────────────────────────────────

_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.I) for p in [
        r"rm\s+-rf\s+/(?!\S)",                          # rm -rf /
        r"rm\s+-rf\s+~/?(\s|$)",                        # rm -rf ~
        r"rm\s+--no-preserve-root",
        r"mkfs\.",                                       # format filesystem
        r"dd\s+.*of=/dev/(sd|nvme|hd)\w*",              # overwrite disk device
        r":\(\)\s*\{.*:\|.*&.*\}",                      # fork bomb
        r"chmod\s+-R\s+777\s+/",
        r">\s*/dev/sda",
        r"format\s+[cC]:",                               # Windows format C:
        r"Remove-Item\s+-Recurse\s+-Force\s+C:\\\\",    # PowerShell nuke
        r"(shutdown|halt|poweroff|reboot)(\s|$)",
        r"curl\s+[^|]*\|\s*(bash|sh)\b",                # curl pipe to shell
        r"wget\s+.*-O\s*-\s*\|",                        # wget pipe to shell
    ]
]


def check_blocklist(command: str) -> str | None:
    """Return the matched pattern string if blocked, else None."""
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return pattern.pattern
    return None


# ─── Env sanitization ────────────────────────────────────────────────────────

# Keys that cannot be overwritten — overwrite attempts are silently dropped.
_PROTECTED_KEYS: frozenset[str] = frozenset({
    "PATH",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "NODE_OPTIONS",
    "PYTHONSTARTUP",
    "PYTHONPATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
})

# Keys whose values are redacted in audit logs (but passed to the process).
_SECRET_KEY_PATTERN = re.compile(
    r"SECRET|PASSWORD|TOKEN|KEY|CREDENTIAL|AUTH|PASS|PWD", re.I
)

# Pattern to detect inline secrets in command strings (for audit redaction).
_INLINE_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                  # AWS access key
    re.compile(r"ghp_[A-Za-z0-9]{36}"),               # GitHub PAT
    re.compile(r"--(password|secret|token|key|auth)[\s=]+\S+", re.I),
]


def sanitize_env(
    user_env: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """Return (safe_env, redacted_keys).

    safe_env       — env dict with protected keys removed.
    redacted_keys  — list of key names whose values were redacted in the audit log.
    """
    safe: dict[str, str] = {}
    redacted: list[str] = []

    for key, value in user_env.items():
        if key in _PROTECTED_KEYS:
            # Drop silently — protected key.
            continue
        safe[key] = value
        if _SECRET_KEY_PATTERN.search(key):
            redacted.append(key)

    return safe, redacted


def redact_command_for_log(command: str) -> str:
    """Return command with inline secrets replaced by [REDACTED] for audit log."""
    result = command
    for pattern in _INLINE_SECRET_PATTERNS:
        result = pattern.sub(lambda m: m.group(0).split(m.group(0)[-10:])[0] + "[REDACTED]", result)
    return result
