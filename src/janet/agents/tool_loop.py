"""Drives one user turn to completion: call the model, execute any requested
tool calls, feed results back, and repeat until a plain-text reply comes back."""

from typing import Any, Callable

from janet.agents.base import LLMProvider, Message
from janet.agents.tools import TOOLS


def run_turn(
    provider: LLMProvider,
    history: list[Message],
    tools: list[Callable[..., Any]] = TOOLS,
    max_iterations: int = 5,
) -> str:
    """Runs one user turn against `provider`, mutating `history` in place with
    the assistant/tool messages produced along the way. Returns the final
    assistant reply text. Raises RuntimeError if `max_iterations` is exceeded
    without a final plain-text answer (guards against a runaway tool-call loop)."""
    registry = {fn.__name__: fn for fn in tools}
    for _ in range(max_iterations):
        response = provider.generate(history, tools=tools)
        if not response["tool_calls"]:
            history.append({"role": "assistant", "content": response["content"]})
            return response["content"]

        history.append(
            {"role": "assistant", "content": response["content"], "tool_calls": response["tool_calls"]}
        )
        for call in response["tool_calls"]:
            name = call["function"]["name"]
            fn = registry.get(name)
            try:
                result = fn(**call["function"]["arguments"]) if fn else f"Error: unknown tool {name!r}."
            except Exception as exc:
                result = f"Error running tool {name!r}: {exc}"
            tool_message: Message = {"role": "tool", "tool_name": name, "content": str(result)}
            if "id" in call:
                tool_message["tool_call_id"] = call["id"]
            history.append(tool_message)

    raise RuntimeError("Tool-calling loop exceeded max iterations without a final answer.")
