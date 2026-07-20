"""Plain-English definitions the tutor can hand back through ``explain_term``.

These are words, not numbers, so they don't touch hard rule #1: nothing here is a figure
about anyone's money. The point is a consistent voice, so the tutor defines "cost basis"
the same way the rest of the app does.

This mirrors ``web/lib/glossary.ts`` on the frontend. The two are kept in sync by hand; if
you add or reword a term in one, do the same in the other.
"""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    "market cap": (
        "What the whole company is worth, if you bought every share of it at today's price. "
        "It's the quickest way to tell a giant company from a small one."
    ),
    "p/e ratio": (
        "The share price divided by the company's yearly profit per share. Roughly: how many "
        "years of today's profits you're paying for. A high number means people expect the "
        "company to grow."
    ),
    "dividend yield": (
        "Some companies pay you a slice of their profits just for holding the shares. The yield "
        "is how much that adds up to in a year, as a percent of the share price."
    ),
    "volume": (
        "How many shares changed hands today. Heavy volume means a lot of people are trading it, "
        "which usually means something happened."
    ),
    "etf": (
        "One fund that holds a whole basket of stocks. Buying a single share of it spreads your "
        "money across everything inside, so you're not betting on one company."
    ),
    "ticker": (
        "The short code a stock trades under. Apple is AAPL, Microsoft is MSFT. It's just a name."
    ),
    "market order": (
        "Buy or sell right now, at whatever the price currently is. The simplest kind of order: "
        "it happens straight away, but you take whatever price the market is at."
    ),
    "limit order": (
        "You name your price and wait. A limit buy only goes through if the price drops to your "
        "number; a limit sell only if it rises to it. You never pay more than you meant to, but "
        "it might never happen at all."
    ),
    "fractional shares": (
        "You don't have to buy a whole share. If a share costs $500 and you put in $50, you get a "
        "tenth of one. It works exactly the same, just smaller."
    ),
    "cost basis": (
        "The total you paid for the shares you own. Compare it to what they're worth now and the "
        "difference is your profit or loss."
    ),
    "average cost": (
        "If you bought the same stock more than once at different prices, this is the average you "
        "paid per share."
    ),
    "gain/loss": (
        "The difference between what your shares are worth now and what you paid. It's only on "
        "paper until you sell."
    ),
    "allocation": (
        "How your money is split up across the things you own. If one stock is most of your money, "
        "that's a big bet on one company."
    ),
    "diversification": (
        "Spreading your money across different things, so one of them going badly doesn't sink you."
    ),
    "benchmark": (
        "A yardstick to measure yourself against. Ours is the S&P 500, because the real question "
        "isn't 'did I make money', it's 'did I do better than just buying the whole market'."
    ),
    "s&p 500": (
        "An index of 500 of the largest US companies, treated as one basket. When people say 'the "
        "market went up', this is usually what they mean. You can buy the whole thing in one go."
    ),
    "volatility": (
        "How much a price jumps around. High volatility means big swings in both directions, which "
        "is another way of saying you can't count on it in the short run."
    ),
}


def define(term: str) -> str | None:
    """Return the plain-English definition of ``term`` (case-insensitive), or ``None``."""
    return GLOSSARY.get(term.strip().lower())
