"""Tools Janet's model can call, plus a schema builder for providers that need
a hand-built JSON schema instead of Ollama's built-in function introspection.

Adding a tool: write a typed function with a Google-style ``Args:`` docstring
section and append it to ``TOOLS``. Nothing else needs to change.
"""

import inspect
import re
from datetime import datetime
from typing import Any, Callable

from ddgs import DDGS

from janet import memory

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
    return "Got it, I'll remember that."


TOOLS: list[Callable[..., Any]] = [get_current_datetime, web_search, echo, remember_fact]
