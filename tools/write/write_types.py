from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class WriteParams:
    path: str
    content: str
    encoding: str = "utf-8"
    create_parents: bool = True
    overwrite: bool = True
    atomic: bool = True
    max_bytes: int = 10_485_760         # 10 MB


WriteErrorCode = Literal[
    "BLOCKED_PATH",
    "FILE_EXISTS",
    "SIZE_LIMIT_EXCEEDED",
    "PARENT_NOT_FOUND",
    "ENCODING_ERROR",
    "PERMISSION_DENIED",
    "INTERNAL",
]


@dataclass(kw_only=True)
class WriteBase:
    status: str
    path: str


@dataclass(kw_only=True)
class WriteResultDone(WriteBase):
    status: Literal["done"] = "done"
    bytes_written: int = 0
    lines_written: int = 0
    created: bool = False
    overwritten: bool = False
    atomic: bool = True


@dataclass(kw_only=True)
class WriteResultError(WriteBase):
    status: Literal["error"] = "error"
    error_code: WriteErrorCode = "INTERNAL"
    error_message: str = ""


WriteResult = Union[WriteResultDone, WriteResultError]
