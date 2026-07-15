"""Unit tests for the number-provenance guard.

This is the enforceable core of hard rule #1: given the tutor's answer and everything the
tools returned, prove that every number in the answer traces back to a tool figure. These
tests are where "the tutor never states a number it wasn't handed" is actually pinned down.
"""

from __future__ import annotations

from services.tutor.guard import unaccounted_numbers


def test_a_clean_answer_has_no_stray_numbers() -> None:
    tools = [{"cash": 1204.0, "total_gain_loss_percent": 2.4}]
    text = "You've got $1,204 in cash and you're up 2.4%."
    assert unaccounted_numbers(text, tools) == []


def test_an_invented_number_is_flagged() -> None:
    tools = [{"cash": 1000.0}]
    text = "Your P/E ratio is about 18.5."
    assert unaccounted_numbers(text, tools) == ["18.5"]


def test_rounding_a_tool_figure_is_allowed() -> None:
    # The tool returned 1203.87; the tutor rounding it to $1,204 is fine.
    tools = [{"total_value": 1203.87}]
    assert unaccounted_numbers("About $1,204 in total.", tools) == []


def test_numbers_inside_returned_news_count_as_accounted() -> None:
    tools = [{"articles": [{"headline": "Apple jumps 5% after earnings"}]}]
    assert unaccounted_numbers("The news says it jumped 5%.", tools) == []
    # A number that appeared in no tool output is still caught.
    assert unaccounted_numbers("It jumped 5% and 9%.", tools) == ["9"]


def test_the_sp_500_name_is_not_flagged() -> None:
    assert unaccounted_numbers("Compared to the S&P 500 basket...", []) == []


def test_sign_matters() -> None:
    tools = [{"gain_loss_percent": -3.2}]
    assert unaccounted_numbers("You're down -3.2%.", tools) == []
    # Stated as a positive, it's a different claim and no tool returned +3.2.
    assert unaccounted_numbers("You're up 3.2%.", tools) == ["3.2"]


def test_a_boolean_is_not_a_figure() -> None:
    # {"available": True} must not make "1" an accounted-for number.
    assert unaccounted_numbers("There is 1 issue.", [{"available": True}]) == ["1"]


def test_counts_from_a_tool_are_accounted() -> None:
    assert unaccounted_numbers("You hold 3 stocks.", [{"position_count": 3}]) == []
