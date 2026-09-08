"""Concrete LLMProvider implementations."""

import json
from typing import Any, Callable

import ollama
from google import genai
from google.genai import types as gtypes
from groq import Groq

from janet import config
from janet.agents.base import LLMProvider, LLMResponse, Message, ToolCall
from janet.agents.tools import build_tool_schema


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = config.OLLAMA_MODEL) -> None:
        self._model = model

    def generate(self, messages: list[Message], tools: list[Callable[..., Any]] | None = None) -> LLMResponse:
        try:
            response = ollama.chat(model=self._model, messages=messages, tools=tools)
        except Exception as exc:
            raise RuntimeError(
                f"Could not reach Ollama (model={self._model!r}). "
                "Is `ollama serve` running and has `ollama pull qwen3:8b` completed?"
            ) from exc

        tool_calls: list[ToolCall] = [
            {"function": {"name": tc.function.name, "arguments": dict(tc.function.arguments)}}
            for tc in (response.message.tool_calls or [])
        ]
        return {"content": response.message.content or "", "tool_calls": tool_calls}


class GroqProvider(LLMProvider):
    def __init__(self, model: str = config.GROQ_MODEL) -> None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Get a key from https://console.groq.com/keys and set it in .env.")
        self._client = Groq(api_key=config.GROQ_API_KEY)
        self._model = model

    def generate(self, messages: list[Message], tools: list[Callable[..., Any]] | None = None) -> LLMResponse:
        groq_tools = [{"type": "function", "function": build_tool_schema(fn)} for fn in (tools or [])] or None
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=_messages_to_groq(messages),
                tools=groq_tools,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not reach Groq (model={self._model!r}): {exc}") from exc

        msg = response.choices[0].message
        tool_calls: list[ToolCall] = [
            {
                "id": tc.id,
                "function": {"name": tc.function.name, "arguments": json.loads(tc.function.arguments)},
            }
            for tc in (msg.tool_calls or [])
        ]
        return {"content": msg.content or "", "tool_calls": tool_calls}


def _messages_to_groq(messages: list[Message]) -> list[dict]:
    """Translate our provider-agnostic Message list into Groq's OpenAI-style
    wire format: tool_calls' arguments become a JSON string, and tool-result
    messages are matched back to their call via tool_call_id (not name)."""
    groq_messages: list[dict] = []
    for m in messages:
        if m["role"] == "tool":
            groq_messages.append(
                {"role": "tool", "content": m["content"], "tool_call_id": m.get("tool_call_id", "")}
            )
        elif m["role"] == "assistant" and m.get("tool_calls"):
            groq_messages.append(
                {
                    "role": "assistant",
                    "content": m["content"] or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": json.dumps(tc["function"]["arguments"]),
                            },
                        }
                        for tc in m["tool_calls"]
                    ],
                }
            )
        else:
            groq_messages.append({"role": m["role"], "content": m["content"]})
    return groq_messages


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = config.GEMINI_MODEL) -> None:
        if not config.GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Get a key from https://ai.google.dev/gemini-api/docs/api-key "
                "and set it in .env."
            )
        self._client = genai.Client(api_key=config.GOOGLE_API_KEY)
        self._model = model

    def generate(self, messages: list[Message], tools: list[Callable[..., Any]] | None = None) -> LLMResponse:
        system_instruction, contents = _messages_to_gemini(messages)
        gemini_tools = None
        if tools:
            declarations = [
                gtypes.FunctionDeclaration(
                    name=schema["name"],
                    description=schema["description"],
                    parameters_json_schema=schema["parameters"],
                )
                for schema in (build_tool_schema(fn) for fn in tools)
            ]
            gemini_tools = [gtypes.Tool(function_declarations=declarations)]

        gen_config = gtypes.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = self._client.models.generate_content(model=self._model, contents=contents, config=gen_config)
        except Exception as exc:
            raise RuntimeError(f"Could not reach Gemini (model={self._model!r}): {exc}") from exc

        tool_calls: list[ToolCall] = []
        parts = response.candidates[0].content.parts if response.candidates and response.candidates[0].content else []
        for part in parts or []:
            if not part.function_call:
                continue
            call: ToolCall = {
                "function": {"name": part.function_call.name, "arguments": dict(part.function_call.args or {})}
            }
            if part.thought_signature:
                call["signature"] = part.thought_signature
            tool_calls.append(call)
        return {"content": response.text or "", "tool_calls": tool_calls}


def _messages_to_gemini(messages: list[Message]) -> tuple[str | None, list[gtypes.Content]]:
    """Translate our provider-agnostic Message list into Gemini's Content/Part
    format. The system prompt has no place in `contents` for Gemini — it's
    pulled out and returned separately for `GenerateContentConfig.system_instruction`."""
    system_instruction: str | None = None
    contents: list[gtypes.Content] = []
    for m in messages:
        if m["role"] == "system":
            system_instruction = m["content"]
        elif m["role"] == "tool":
            # Gemini's generate_content rejects role="tool" despite some docs suggesting it
            # (confirmed live: "Role 'tool' is not supported") — function responses go under "user".
            part = gtypes.Part.from_function_response(name=m["tool_name"], response={"result": m["content"]})
            contents.append(gtypes.Content(role="user", parts=[part]))
        elif m["role"] == "assistant" and m.get("tool_calls"):
            parts = []
            for tc in m["tool_calls"]:
                part = gtypes.Part.from_function_call(name=tc["function"]["name"], args=tc["function"]["arguments"])
                if "signature" in tc:
                    # Must be replayed verbatim or Gemini 400s with "missing thought_signature".
                    part.thought_signature = tc["signature"]
                parts.append(part)
            contents.append(gtypes.Content(role="model", parts=parts))
        else:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append(gtypes.Content(role=role, parts=[gtypes.Part.from_text(text=m["content"])]))
    return system_instruction, contents
