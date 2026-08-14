"""The tutor's LLM, kept behind an interface so the model is not baked into the app.

Same shape as the market client: a ``Protocol`` for the slice we actually use, one error
contract (``TutorError``), an ``lru_cache`` factory, and a fake in tests. The engine only
ever sees the neutral message and tool types defined here, so swapping the model (or the
whole provider) stays a change inside this one file. The concrete provider wraps OpenAI's
chat completions with tool calling.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Sequence
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

    def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> Generator[str, None, Completion]:
        """Run one round, yielding text as it arrives; the return value is the full completion.

        The default just delegates to ``complete`` and yields the answer in one piece, so any
        provider streams *something* without extra work. A provider that can truly stream (the
        OpenAI one below) overrides this to yield token by token. A round that only calls tools
        yields nothing, since its content is empty; the engine relies on that to avoid leaking a
        tool round's text to the user.
        """
        completion = self.complete(system=system, messages=messages, tools=tools)
        if completion.text:
            yield completion.text
        return completion


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

    def stream(
        self, *, system: str, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> Generator[str, None, Completion]:
        """Stream one round from OpenAI, yielding each content delta as it arrives.

        Tool calls stream as fragments across many chunks, so we stitch them back together by
        index and only surface them at the end, as the completed Completion. Content chunks are
        yielded live; a tool round carries no content, so nothing is yielded for one.
        """
        payload = [{"role": "system", "content": system}, *(_to_openai(m) for m in messages)]
        kwargs: dict[str, Any] = {"model": self._model, "messages": payload, "stream": True}
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
        if tool_specs:
            kwargs["tools"] = tool_specs
            kwargs["tool_choice"] = "auto"

        text_parts: list[str] = []
        fragments: dict[int, dict[str, str]] = {}
        try:
            for chunk in self._client.chat.completions.create(**kwargs):
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    text_parts.append(delta.content)
                    yield delta.content
                for call in getattr(delta, "tool_calls", None) or []:
                    _accumulate_tool_call(fragments, call)
        except OpenAIError as exc:
            raise TutorError(
                "The tutor is having trouble reaching its brain right now. Try again in a moment."
            ) from exc

        calls = tuple(
            ToolCall(
                id=fragment["id"],
                name=fragment["name"],
                arguments=_parse_args(fragment["arguments"]),
            )
            for _, fragment in sorted(fragments.items())
        )
        return Completion(text="".join(text_parts), tool_calls=calls)


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


def _accumulate_tool_call(fragments: dict[int, dict[str, str]], call: Any) -> None:
    """Stitch a streamed tool-call fragment onto the one being built at its index.

    OpenAI streams a tool call in pieces: the id and name arrive early, the JSON arguments dribble
    in across later chunks. We key by ``call.index`` and concatenate the arguments as they come.
    """
    fragment = fragments.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
    if getattr(call, "id", None):
        fragment["id"] = call.id
    function = getattr(call, "function", None)
    if function is not None:
        if getattr(function, "name", None):
            fragment["name"] = function.name
        if getattr(function, "arguments", None):
            fragment["arguments"] += function.arguments
