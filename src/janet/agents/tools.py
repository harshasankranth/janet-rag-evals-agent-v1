"""Tools Janet's model can call, plus a schema builder for providers that need
a hand-built JSON schema instead of Ollama's built-in function introspection.

Adding a tool: write a typed function with a Google-style ``Args:`` docstring
section and append it to ``TOOLS``. Nothing else needs to change.
"""

import inspect
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ddgs import DDGS

from janet import memory
from janet.rag.ingest import read_file
from janet.rag.retriever import get_retriever

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _parse_docstring_args(func: Callable[..., Any]) -> dict[str, str]:
    """Extract per-argument descriptions from a Google-style 'Args:' docstring section."""
    doc = inspect.getdoc(func) or ""
    args: dict[str, str] = {}
    in_args = False
    last_key = None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("args:"):
            in_args = True
            continue
        if not in_args:
            continue
        match = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", stripped)
        if match:
            last_key, desc = match.group(1), match.group(2)
            args[last_key] = desc
        elif last_key and stripped:
            args[last_key] += " " + stripped
    return args


def build_tool_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Build a {name, description, parameters} JSON-schema triple from a typed,
    docstring-annotated function, for providers (Groq, Gemini) that need a
    hand-built schema instead of Ollama's built-in introspection."""
    arg_docs = _parse_docstring_args(func)
    doc = inspect.getdoc(func) or ""
    description = doc.split("Args:")[0].strip().replace("\n", " ")

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(func).parameters.items():
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else str
        properties[name] = {
            "type": _TYPE_MAP.get(annotation, "string"),
            "description": arg_docs.get(name, ""),
        }
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "name": func.__name__,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


def get_current_datetime() -> str:
    """Get the current local date and time.

    Returns the current date and time as a human-readable string. Use this
    whenever the user asks what day, date, or time it is.
    """
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")


def web_search(query: str, max_results: int = 3) -> str:
    """Search the web for up-to-date information not in your own knowledge.

    Args:
        query: The search query text.
        max_results: Maximum number of results to return.
    """
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as exc:
        return f"Web search failed: {exc}"
    if not results:
        return "No results found."
    return "\n".join(f"{r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})" for r in results)


def echo(text: str) -> str:
    """Echo back the given text, used to verify tool-calling works end to end.

    Args:
        text: The text to echo back.
    """
    return text


def remember_fact(fact: str) -> str:
    """Permanently remember something about the user for future conversations,
    even after this session ends — their name, preferences, ongoing projects,
    or other durable context. Only use this for things worth recalling long
    term, not one-off details that only matter for the current exchange.

    Args:
        fact: The fact to remember, written plainly and completely so it
            still makes sense on its own later (e.g. "The user's name is
            Harsha" rather than just "Harsha").
    """
    memory.remember(fact)
    # Also index it, so it stays recallable after the JSON list's FIFO cap evicts it.
    if (retriever := get_retriever()) is not None:
        retriever.add_memory(fact)
    return "Got it, I'll remember that."


def search_knowledge(query: str, source: str = "all") -> str:
    """Search the user's own knowledge base: documents and notes they have
    indexed, facts you have remembered about them, and your past
    conversations with them. Use this when the user asks about their own
    files, notes, or something you discussed before, or whenever the
    answer is likely personal to them rather than general knowledge.

    Args:
        query: What to look for, phrased as a short descriptive search
            query (e.g. "lease pet policy" or "book recommendation last month").
        source: Where to search: "all", "documents", "memories", or
            "conversations".
    """
    retriever = get_retriever()
    if retriever is None:
        return "The knowledge base is not available right now."
    kinds = {"documents": {"document"}, "memories": {"memory"}, "conversations": {"conversation"}}.get(source)
    return retriever.search(query, kinds=kinds)


_READ_DOCUMENT_MAX_CHARS = 30_000  # keeps one whole-document read from blowing up the context window


def list_documents() -> str:
    """List the documents and files the user has shared with you or indexed
    into the knowledge base. Use this when the user asks what files you
    have, or to find the exact name of a document before reading it.
    """
    retriever = get_retriever()
    if retriever is None:
        return "The knowledge base is not available right now."
    sources = retriever.store.sources()
    if not sources:
        return "No documents have been shared yet."
    return "\n".join(Path(s).name for s in sources)


def read_document(name: str = "") -> str:
    """Read the full text of one of the user's documents. Use this to
    summarise, explain, or answer broad questions about a whole document
    (e.g. "summarise the PDF I just sent"). For a specific detail, prefer
    search_knowledge instead.

    Args:
        name: The document's file name, or part of it (e.g. "lease" for
            lease.pdf). Leave empty to read the most recently shared document.
    """
    retriever = get_retriever()
    if retriever is None:
        return "The knowledge base is not available right now."
    sources = list(retriever.store.sources())  # insertion order, so the last one is the newest
    if not sources:
        return "No documents have been shared yet."
    if name.strip():
        matches = [s for s in sources if name.strip().lower() in Path(s).name.lower()]
        if not matches:
            return f"No document matching {name!r}. Available: {', '.join(Path(s).name for s in sources)}"
        source = matches[-1]
    else:
        source = sources[-1]
    try:
        text = read_file(Path(source))
    except Exception as exc:
        return f"Could not read {Path(source).name}: {exc}"
    if len(text) > _READ_DOCUMENT_MAX_CHARS:
        text = text[:_READ_DOCUMENT_MAX_CHARS] + "\n[...document truncated — use search_knowledge for later parts]"
    return f"[{Path(source).name}]\n{text}"


TOOLS: list[Callable[..., Any]] = [
    get_current_datetime,
    web_search,
    echo,
    remember_fact,
    search_knowledge,
    list_documents,
    read_document,
]
