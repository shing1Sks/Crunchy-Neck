"""
browser.py — Chrome launcher for Scout (computer agent).

Launches Chrome with a persistent user-data-dir so login sessions survive
across runs. Each named profile gets its own isolated user-data directory at:

    ~/.computer-agent/profiles/<profile_name>/user-data

Usage:
    from computer_agent.browser import launch_chrome
    proc = launch_chrome(profile_name="default")   # returns Popen handle

Chrome is found via:
    1. CHROME_PATH env var (explicit override)
    2. Standard Win32 install paths
    3. RuntimeError if not found
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

_WIN32_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{user}\AppData\Local\Google\Chrome\Application\chrome.exe",
]

_CHROME_READY_TIMEOUT = 15   # seconds to wait for DevTools endpoint
_CHROME_POLL_INTERVAL = 0.3


def find_chrome() -> str:
    """
    Return the path to the Chrome executable.

    Checks CHROME_PATH env var first, then standard Win32 locations.
    Raises RuntimeError if Chrome cannot be found.
    """
    env_path = os.environ.get("CHROME_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    username = os.environ.get("USERNAME", "")
    candidates = [p.replace("{user}", username) for p in _WIN32_CHROME_PATHS]

    for path in candidates:
        if Path(path).exists():
            return path

    raise RuntimeError(
        "Chrome not found. Install Google Chrome or set CHROME_PATH in .env\n"
        f"Searched: {candidates}"
    )


def launch_chrome(
    profile_name: str = "default",
    port: int = 9222,
) -> subprocess.Popen:
    """
    Launch Chrome with a persistent profile and remote debugging enabled.

    Blocks until Chrome's DevTools endpoint is ready (up to 15s).
    Returns the Popen handle — caller can keep it to terminate Chrome later.

    Args:
        profile_name: Name of the Chrome profile to use. Each profile has its
                      own login sessions, cookies, and extensions.
        port:         Remote debugging port (default 9222).
    """
    user_data_dir = (
        Path.home() / ".computer-agent" / "profiles" / profile_name / "user-data"
    )
    user_data_dir.mkdir(parents=True, exist_ok=True)

    chrome_path = find_chrome()

    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    _wait_for_chrome(port)
    return proc


def _wait_for_chrome(port: int) -> None:
    """Poll the DevTools /json/version endpoint until Chrome is ready."""
    url = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + _CHROME_READY_TIMEOUT

    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=1)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(_CHROME_POLL_INTERVAL)

    raise RuntimeError(
        f"Chrome did not become ready on port {port} within {_CHROME_READY_TIMEOUT}s"
    )
