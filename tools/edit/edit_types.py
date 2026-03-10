from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class EditParams:
    path: str
    old: str
    new: str
    encoding: str = "utf-8"
    allow_multiple: bool = False
    dry_run: bool = False
    atomic: bool = True


EditErrorCode = Literal[
    "BLOCKED_PATH",
    "NOT_FOUND",
    "IS_DIRECTORY",
    "OLD_NOT_FOUND",
    "OLD_AMBIGUOUS",
    "ENCODING_ERROR",
    "PERMISSION_DENIED",
    "INTERNAL",
]


@dataclass(kw_only=True)
class EditBase:
    status: str
    path: str


@dataclass(kw_only=True)
class EditResultDone(EditBase):
    status: Literal["done"] = "done"
    replacements_made: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    dry_run: bool = False
    diff_preview: str | None = None     # unified diff, always populated


@dataclass(kw_only=True)
class EditResultError(EditBase):
    status: Literal["error"] = "error"
    error_code: EditErrorCode = "INTERNAL"
    error_message: str = ""


EditResult = Union[EditResultDone, EditResultError]
