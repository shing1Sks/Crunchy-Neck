from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass
class ReadParams:
    path: str
    encoding: str = "utf-8"
    max_bytes: int = 1_048_576          # 1 MB
    start_line: int = 0
    num_lines: int | None = None
    binary: Literal["error", "base64", "skip"] = "error"


ReadErrorCode = Literal[
    "BLOCKED_PATH",
    "NOT_FOUND",
    "IS_DIRECTORY",
    "BINARY_FILE",
    "ENCODING_ERROR",
    "PERMISSION_DENIED",
    "INTERNAL",
]


@dataclass(kw_only=True)
class ReadBase:
    status: str
    path: str


@dataclass(kw_only=True)
class ReadResultDone(ReadBase):
    status: Literal["done"] = "done"
    content: str = ""
    encoding: str = "utf-8"
    size_bytes: int = 0
    total_lines: int = 0
    lines_returned: int = 0
    truncated: bool = False
    truncation_note: str | None = None


@dataclass(kw_only=True)
class ReadResultError(ReadBase):
    status: Literal["error"] = "error"
    error_code: ReadErrorCode = "INTERNAL"
    error_message: str = ""


ReadResult = Union[ReadResultDone, ReadResultError]
