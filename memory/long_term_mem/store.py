from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_chroma_lock = threading.Lock()


class ChromaUnavailableError(RuntimeError):
    """Raised when chromadb cannot be imported or the client cannot start."""


class LongTermMemStore:
    """Thread-safe wrapper around a ChromaDB persistent collection."""

    COLLECTION_NAME = "long_term"

    def __init__(self, chroma_dir: str) -> None:
        self._chroma_dir = chroma_dir
        self._client: Any = None
        self._collection: Any = None

    def _ensure_init(self) -> None:
        if self._collection is not None:
            return
        with _chroma_lock:
            if self._collection is not None:
                return
            try:
                import chromadb
            except ImportError as exc:
                raise ChromaUnavailableError(
                    f"chromadb is not installed. Run: pip install 'chromadb>=0.4,<2'. "
                    f"Original error: {exc}"
                ) from exc

            try:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
                ef = DefaultEmbeddingFunction()
            except Exception:
                ef = None

            Path(self._chroma_dir).mkdir(parents=True, exist_ok=True)
            try:
                client = chromadb.PersistentClient(path=self._chroma_dir)
                kwargs: dict[str, Any] = {"name": self.COLLECTION_NAME}
                if ef is not None:
                    kwargs["embedding_function"] = ef
                self._collection = client.get_or_create_collection(**kwargs)
                self._client = client
            except Exception as exc:
                raise ChromaUnavailableError(
                    f"ChromaDB PersistentClient failed at {self._chroma_dir!r}: {exc}"
                ) from exc

    def store(
        self,
        content: str,
        *,
        agent_session_id: str,
        tags: list[str] | None = None,
    ) -> tuple[str, str]:
        """Embed and store content. Returns (memory_id, iso_timestamp)."""
        self._ensure_init()
        memory_id = str(uuid.uuid4())
        ts = datetime.now(tz=timezone.utc).isoformat()
        metadata: dict[str, Any] = {
            "timestamp": ts,
            "session_id": agent_session_id,
            "tags": ",".join(tags) if tags else "",
        }
        self._collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[metadata],
        )
        return memory_id, ts

    def query(
        self,
        query_text: str,
        n_results: int = 5,
    ) -> tuple[list[dict[str, Any]], int]:
        """Semantic similarity search. Returns (hits, total_count)."""
        self._ensure_init()
        total = self._collection.count()
        if total == 0:
            return [], 0

        actual_n = min(n_results, total)
        results = self._collection.query(
            query_texts=[query_text],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        for mem_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            raw_tags = meta.get("tags", "")
            hits.append({
                "memory_id": mem_id,
                "content": doc,
                "distance": float(dist),
                "timestamp": meta.get("timestamp", ""),
                "tags": [t for t in raw_tags.split(",") if t] if raw_tags else [],
                "session_id": meta.get("session_id", ""),
            })
        return hits, total

    def list_all(self) -> tuple[list[dict[str, Any]], int]:
        """Return all memories (direct get, no embedding query)."""
        self._ensure_init()
        total = self._collection.count()
        if total == 0:
            return [], 0
        results = self._collection.get(include=["documents", "metadatas"])
        items: list[dict[str, Any]] = []
        for mem_id, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
            raw_tags = meta.get("tags", "")
            items.append({
                "memory_id": mem_id,
                "content": doc,
                "distance": 0.0,
                "timestamp": meta.get("timestamp", ""),
                "tags": [t for t in raw_tags.split(",") if t] if raw_tags else [],
                "session_id": meta.get("session_id", ""),
            })
        return items, total

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted, False if not found."""
        self._ensure_init()
        existing = self._collection.get(ids=[memory_id])
        if not existing["ids"]:
            return False
        self._collection.delete(ids=[memory_id])
        return True
