from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass
class RememberParams:
    action: Literal["store", "query", "list", "delete"]
    content: str | None = None       # required for action="store"
    query: str | None = None         # required for action="query"
    n_results: int = 5               # for action="query"; clamped to 1–50
    memory_id: str | None = None     # required for action="delete"
    tags: list[str] | None = None    # optional for action="store"


RememberErrorCode = Literal[
    "MISSING_CONTENT",
    "MISSING_QUERY",
    "MISSING_MEMORY_ID",
    "MEMORY_NOT_FOUND",
    "CHROMA_UNAVAILABLE",
    "CHROMA_ERROR",
    "INVALID_ACTION",
    "INTERNAL",
]


@dataclass
class MemoryHit:
    memory_id: str
    content: str
    distance: float
    timestamp: str
    tags: list[str]
    session_id: str


@dataclass(kw_only=True)
class RememberBase:
    status: str
    action: str


@dataclass(kw_only=True)
class RememberResultStored(RememberBase):
    status: Literal["stored"] = "stored"
    memory_id: str = ""
    content_preview: str = ""        # first 120 chars of stored content
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""              # ISO-8601 UTC


@dataclass(kw_only=True)
class RememberResultQueried(RememberBase):
    status: Literal["queried"] = "queried"
    query: str = ""
    hits: list[MemoryHit] = field(default_factory=list)
    total_in_collection: int = 0


@dataclass(kw_only=True)
class RememberResultListed(RememberBase):
    status: Literal["listed"] = "listed"
    memories: list[MemoryHit] = field(default_factory=list)
    total: int = 0


@dataclass(kw_only=True)
class RememberResultDeleted(RememberBase):
    status: Literal["deleted"] = "deleted"
    memory_id: str = ""


@dataclass(kw_only=True)
class RememberResultError(RememberBase):
    status: Literal["error"] = "error"
    error_code: RememberErrorCode = "INTERNAL"
    error_message: str = ""


RememberResult = Union[
    RememberResultStored,
    RememberResultQueried,
    RememberResultListed,
    RememberResultDeleted,
    RememberResultError,
]
