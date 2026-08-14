"""Running one turn of the tutor: let the model call tools, then narrate what they returned.

The model can ask for figures but never computes them. The tools in ``services/tutor/tools.py``
are the only source of numbers, and each is scoped to one account. This loop wires the two
together: it offers the model the tools, runs any it calls, feeds the results back, and repeats
until the model answers in prose. Every tool result is also collected so the provenance guard
can check that the answer only quotes numbers a tool actually returned.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from services.tutor.guard import unaccounted_numbers
from services.tutor.prompt import SYSTEM_PROMPT
from services.tutor.provider import (
    AssistantMessage,
    Message,
    ToolMessage,
    TutorProvider,
    UserMessage,
)
from services.tutor.tools import Tool

logger = logging.getLogger(__name__)

# A hard cap on tool rounds so a confused model can't loop forever calling tools.
MAX_ROUNDS = 6

_FALLBACK = "I couldn't put an answer together just now. Try asking again."


@dataclass(frozen=True)
class Turn:
    """One message from the client's side of the conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class TutorAnswer:
    """The tutor's reply to a turn."""

    reply: str


def run_tutor(
    provider: TutorProvider, tools: Sequence[Tool], conversation: Sequence[Turn]
) -> TutorAnswer:
    """Answer the latest turn, letting the model call the (account-scoped) tools as it needs."""
    by_name = {tool.schema.name: tool for tool in tools}
    schemas = [tool.schema for tool in tools]
    messages: list[Message] = [_seed(turn) for turn in conversation]
    tool_outputs: list[Any] = []

    for _ in range(MAX_ROUNDS):
        completion = provider.complete(system=SYSTEM_PROMPT, messages=messages, tools=schemas)
        if not completion.tool_calls:
            return _answer(completion.text, tool_outputs)

        messages.append(AssistantMessage(content=completion.text, tool_calls=completion.tool_calls))
        for call in completion.tool_calls:
            tool = by_name.get(call.name)
            result = tool.run(call.arguments) if tool else {"error": f"Unknown tool {call.name}."}
            tool_outputs.append(result)
            messages.append(ToolMessage(tool_call_id=call.id, content=json.dumps(result)))

    # Out of rounds: one more call with no tools, so the model has to answer with what it has.
    final = provider.complete(system=SYSTEM_PROMPT, messages=messages, tools=[])
    return _answer(final.text, tool_outputs)


def stream_tutor(
    provider: TutorProvider, tools: Sequence[Tool], conversation: Sequence[Turn]
) -> Iterator[str]:
    """Answer the latest turn like ``run_tutor``, but yield the reply's text as it streams.

    Same loop: the model may call the (account-scoped) tools, whose results are fed back until it
    answers in prose. Each round is streamed, so the final prose reaches the caller token by
    token. A tool round yields nothing (its content is empty), so only the answer is forwarded.
    The provenance guard runs once on the assembled text, after the stream ends; it only ever
    logged, so streaming the words before the check is no weaker than before.
    """
    by_name = {tool.schema.name: tool for tool in tools}
    schemas = [tool.schema for tool in tools]
    messages: list[Message] = [_seed(turn) for turn in conversation]
    tool_outputs: list[Any] = []

    for _ in range(MAX_ROUNDS):
        completion = yield from provider.stream(
            system=SYSTEM_PROMPT, messages=messages, tools=schemas
        )
        if not completion.tool_calls:
            _flag_stray_numbers(completion.text, tool_outputs)
            return
        messages.append(AssistantMessage(content=completion.text, tool_calls=completion.tool_calls))
        for call in completion.tool_calls:
            tool = by_name.get(call.name)
            result = tool.run(call.arguments) if tool else {"error": f"Unknown tool {call.name}."}
            tool_outputs.append(result)
            messages.append(ToolMessage(tool_call_id=call.id, content=json.dumps(result)))

    # Out of rounds: one more streamed round with no tools, so the model has to answer.
    completion = yield from provider.stream(system=SYSTEM_PROMPT, messages=messages, tools=[])
    _flag_stray_numbers(completion.text, tool_outputs)


def _seed(turn: Turn) -> Message:
    if turn.role == "assistant":
        return AssistantMessage(content=turn.content)
    return UserMessage(content=turn.content)


def _answer(text: str, tool_outputs: Sequence[Any]) -> TutorAnswer:
    _flag_stray_numbers(text, tool_outputs)
    return TutorAnswer(reply=text or _FALLBACK)


def _flag_stray_numbers(text: str, tool_outputs: Sequence[Any]) -> None:
    """Log any figure in the reply that no tool returned. A monitor, not a censor: the tools plus
    the system prompt are the enforcement, and mangling a false positive is worse than a rare stray
    digit, so we watch it rather than rewrite it (the same call the non-streaming path makes)."""
    stray = unaccounted_numbers(text, tool_outputs)
    if stray:
        logger.warning("Tutor answer stated numbers not traced to a tool: %s", stray)
