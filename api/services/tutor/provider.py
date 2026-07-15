"""The tutor's LLM, kept behind an interface so the model is not baked into the app.

Same shape as the market client: a ``Protocol`` for the slice we actually use, one error
contract (``TutorError``), an ``lru_cache`` factory, and a fake in tests. The engine only
ever sees the neutral message and tool types defined here, so swapping the model (or the
whole provider) stays a change inside this one file. The concrete provider wraps OpenAI's
chat completions with tool calling.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAIError

from config import get_settings


class TutorError(Exception):
    """The tutor's LLM call failed. The message is safe to show a user."""


@dataclass(frozen=True)
class ToolSchema:
    """A tool the model may call: its name, what it's for, and its JSON-schema arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """The model asking to run one tool, with the arguments it chose."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class UserMessage:
    """Something the user said."""

    content: str


@dataclass(frozen=True)
class AssistantMessage:
    """A turn from the model: prose, and any tools it asked to run."""

    content: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ToolMessage:
    """The result of one tool call, fed back to the model."""

    tool_call_id: str
    content: str


Message = UserMessage | AssistantMessage | ToolMessage


@dataclass(frozen=True)
class Completion:
    """One round from the model: prose, plus any tools it wants run before continuing."""

    text: str
    tool_calls: tuple[ToolCall, ...]


class TutorProvider:
    """The slice of an LLM the tutor engine needs: run one round of the conversation.

    A plain class rather than ``typing.Protocol`` so the fake in tests can subclass it and
    inherit this docstring; the engine depends only on the ``complete`` shape.
    """

    def complete(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> Completion:  # pragma: no cover - interface only
        raise NotImplementedError


class OpenAIProvider(TutorProvider):
    """Runs the tutor on OpenAI's chat completions, translating to and from the neutral types."""

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        # The OpenAI client is treated as untyped at this one boundary: its request params
        # are a union of TypedDicts we assemble as plain dicts. Keeping it Any localizes that
        # to this file, while everything the engine touches (the types above) stays typed.
        if client is not None:
            self._client: Any = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> Completion:
        payload = [{"role": "system", "content": system}, *(_to_openai(m) for m in messages)]
        tool_specs = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
        kwargs: dict[str, Any] = {"model": self._model, "messages": payload}
        if tool_specs:
            # tool_choice is only valid alongside tools; the final answer round passes none.
            kwargs["tools"] = tool_specs
            kwargs["tool_choice"] = "auto"
        try:
            response = self._client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            raise TutorError(
                "The tutor is having trouble reaching its brain right now. Try again in a moment."
            ) from exc

        message = response.choices[0].message
        calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=_parse_args(call.function.arguments),
            )
            for call in (message.tool_calls or [])
        )
        return Completion(text=message.content or "", tool_calls=calls)


@lru_cache
def get_tutor_provider() -> TutorProvider | None:
    """The process-wide tutor provider, or ``None`` when no OpenAI key is configured."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAIProvider(api_key=settings.openai_api_key, model=settings.tutor_model)


def _to_openai(message: Message) -> dict[str, Any]:
    """Translate one neutral message into the dict shape OpenAI's API expects."""
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    result: dict[str, Any] = {"role": "assistant", "content": message.content or None}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return result


def _parse_args(raw: str | None) -> dict[str, Any]:
    """Parse a tool call's JSON arguments, tolerating a malformed or empty payload."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
