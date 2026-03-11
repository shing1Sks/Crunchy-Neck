from .remember_tool import remember_command
from .remember_types import RememberParams

TOOL_DEFINITION = {
    "name": "remember",
    "description": (
        "Long-term memory tool. Persist and retrieve information across sessions "
        "using semantic (embedding-based) search.\n\n"
        "Actions:\n"
        "  store  — Embed and save a piece of information. Returns a memory_id.\n"
        "  query  — Semantic similarity search. Returns ranked hits with distance scores.\n"
        "  list   — Return all stored memories (no query required).\n"
        "  delete — Remove a memory by its memory_id.\n\n"
        "Rules:\n"
        "  - Memories persist across agent restarts (stored in .agent/memory/chroma/).\n"
        "  - query distance: 0.0 = identical, 2.0 = completely unrelated (cosine space).\n"
        "  - Tags are free-form strings, useful for browsing by topic.\n"
        "  - n_results is clamped to [1, 50] regardless of what is passed.\n"
        "  - First use will download ~90 MB ONNX model to ~/.cache/chroma/ (one-time)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["store", "query", "list", "delete"],
                "description": "The memory operation to perform.",
            },
            "content": {
                "type": "string",
                "description": "Text to store. Required for action='store'.",
            },
            "query": {
                "type": "string",
                "description": "Search query for semantic retrieval. Required for action='query'.",
            },
            "n_results": {
                "type": "integer",
                "description": "Max number of results for action='query'. Default 5, clamped to 1–50.",
                "default": 5,
            },
            "memory_id": {
                "type": "string",
                "description": "UUID of a specific memory. Required for action='delete'.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional topic tags for action='store'. Helps with manual browsing.",
            },
        },
        "required": ["action"],
    },
}

__all__ = ["remember_command", "RememberParams", "TOOL_DEFINITION"]
