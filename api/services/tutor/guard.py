"""Checking that every number the tutor states came from a tool, not from the model.

Hard rule #1 says numbers come from code. The tools enforce it by being the only source of
figures, and the system prompt tells the model to quote only what a tool returned. This
module is the tripwire that proves it: given the tutor's answer and everything the tools
returned this turn, it flags any number in the answer that can't be traced back to a tool
figure (allowing for the model rounding it for display).

It is deliberately a *monitor*, not a censor. Rewriting the model's wording over a false
positive would be worse than the rare stray digit, so at runtime a violation is logged, not
stripped. Its real teeth are in the tests, where it runs over controlled tool output and
asserts the answer is clean. The enforcement is the architecture; this is how we watch it hold.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# A run of digits, optionally with thousands commas and a decimal part, optional leading minus.
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
# Numbers that read as part of a name or plain English, not as a claim about the user's money.
_INTRINSIC = {Decimal(500)}  # "the S&P 500"


def unaccounted_numbers(text: str, tool_outputs: Iterable[Any]) -> list[str]:
    """The numbers in ``text`` that no tool returned this turn. Empty means the answer is clean.

    ``tool_outputs`` is every payload the tools handed back. A number in the answer is accounted
    for if some tool figure, rounded to the answer's number of decimal places, equals it, so a
    figure quoted exactly or sensibly rounded both pass; a figure the model made up does not.
    """
    allowed = _collect(tool_outputs) | _INTRINSIC
    stray: list[str] = []
    for token in _NUMBER.findall(text):
        value = _parse(token)
        if value is None:
            continue
        if not _accounted(value, allowed):
            stray.append(token)
    return stray


def _collect(tool_outputs: Iterable[Any]) -> set[Decimal]:
    """Every number that appeared anywhere in the tools' output, as exact Decimals.

    Walks the JSON-able payloads and pulls numbers out of both numeric leaves and any strings
    (so a figure embedded in a news headline the tool returned counts as accounted for too).
    """
    found: set[Decimal] = set()
    for output in tool_outputs:
        _walk(output, found)
    return found


def _walk(node: Any, found: set[Decimal]) -> None:
    if isinstance(node, bool):
        return  # bool is an int subclass; a True/False is not a figure
    if isinstance(node, int | float | Decimal):
        value = _parse(str(node))
        if value is not None:
            found.add(value)
    elif isinstance(node, str):
        for token in _NUMBER.findall(node):
            value = _parse(token)
            if value is not None:
                found.add(value)
    elif isinstance(node, dict):
        for child in node.values():
            _walk(child, found)
    elif isinstance(node, list | tuple):
        for child in node:
            _walk(child, found)


def _parse(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None


def _accounted(value: Decimal, allowed: set[Decimal]) -> bool:
    """True if some allowed figure, rounded to ``value``'s decimal places, equals ``value``."""
    # exponent is an int for a real number; the special 'n'/'N'/'F' cases can't occur here
    # because every value is parsed from a plain numeric string, but mypy needs the guard.
    exponent = value.as_tuple().exponent
    places = max(-exponent, 0) if isinstance(exponent, int) else 0
    quantum = Decimal(1).scaleb(-places)
    target = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return any(
        candidate.quantize(quantum, rounding=ROUND_HALF_UP) == target for candidate in allowed
    )
