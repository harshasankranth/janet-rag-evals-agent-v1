"""Provider-agnostic interface for LLM backends."""

from abc import ABC, abstractmethod
from typing import Any, Callable, NotRequired, TypedDict


class ToolCall(TypedDict):
    function: dict[str, Any]  # {"name": str, "arguments": dict[str, Any]}
    id: NotRequired[str]  # populated by Groq (needed to match tool results back); omitted by Ollama/Gemini
    signature: NotRequired[bytes]  # Gemini's opaque "thought signature"; must be replayed verbatim or it 400s


class Message(TypedDict):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: NotRequired[list[ToolCall]]
    tool_name: NotRequired[str]
    tool_call_id: NotRequired[str]  # set when replying to a Groq tool call; ignored by Ollama/Gemini


class LLMResponse(TypedDict):
    content: str
    tool_calls: list[ToolCall]  # empty when the model gave a final plain answer


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[Message], tools: list[Callable[..., Any]] | None = None) -> LLMResponse:
        """Given the conversation so far and optional tools the model may call,
        return the assistant's reply content plus any requested tool calls."""
