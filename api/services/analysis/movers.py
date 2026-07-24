"""What actually moved the number: which of your positions is behind the gain or the loss.

Still the analysis layer, so still plain Python with no LLM anywhere near it. The per-position
profit and loss already existed as a column in the holdings table; this turns it into the one
sentence a beginner can actually read, which is the "plain-language money framing" the product
spec asks for ("you made $240" beats "up 2.4%").

One honesty constraint shapes every line of copy here. These figures are the **unrealized**
profit and loss on what you are holding *right now*. The account's total gain also includes
money already banked from things you sold, so the two do not add up, and a sentence claiming
"that's where your gain came from" would be wrong for anyone who has ever sold a winner. So
every phrasing here describes the current positions and never claims to explain the total.
Adding realized profit per symbol would need a walk over the transactions, which is a bigger
feature than this one.

Hard rule #2 applies as it does everywhere: this names what moved, it never suggests doing
anything about it. A position is described ("your biggest drop"), never judged.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal(0)

# When one position is at least this much of all the movement (measured in either direction),
# it is not merely the biggest, it is basically the whole story, and the copy says so. Below
# this it is reported as the biggest and nothing more.
DOMINANT_SHARE = Decimal("0.6")


@dataclass(frozen=True)
class Mover:
    """One holding and the money it is up or down.

    ``gain_loss`` is ``None`` when the live quote failed, so an unpriced position is left out
    of the story rather than counted as having gone nowhere.
    """

    symbol: str
    gain_loss: Decimal | None


def rank(movers: Iterable[Mover]) -> list[Mover]:
    """The positions that have actually moved, biggest first, in either direction.

    Drops anything unpriced or exactly flat: neither has anything to say. Ties break on the
    symbol so the order is stable, which keeps the sentence from flickering between loads.
    """
    moved = [mover for mover in movers if mover.gain_loss is not None and mover.gain_loss != _ZERO]
    return sorted(moved, key=lambda mover: (-abs(mover.gain_loss or _ZERO), mover.symbol))


def what_moved(movers: Sequence[Mover]) -> str | None:
    """One sentence naming what's moved, or ``None`` when nothing has.

    Pure and total: the same positions always give the same sentence, and it never reads a
    clock, a database or a price.
    """
    ranked = rank(movers)
    if not ranked:
        return None

    biggest = ranked[0]
    # mypy: rank() has already dropped the None gain/loss values.
    amount = biggest.gain_loss or _ZERO
    up = amount > _ZERO

    if len(ranked) == 1:
        lead = f"{biggest.symbol} is your only position that's moved, {_direction(amount)}."
    else:
        total_movement = sum((abs(mover.gain_loss or _ZERO) for mover in ranked), _ZERO)
        dominant = total_movement > _ZERO and abs(amount) / total_movement >= DOMINANT_SHARE
        if dominant:
            side = "gain" if up else "loss"
            lead = (
                f"Almost all of your {side} sits in one stock: "
                f"{biggest.symbol}, {_direction(amount)}."
            )
        else:
            side = "gain" if up else "drop"
            lead = f"Your biggest {side} right now is {biggest.symbol}, {_direction(amount)}."

    # Name the other side too, when there is one. A portfolio that is up overall while
    # something inside it is down is the normal case, and saying so keeps the picture whole.
    other = _first_opposite(ranked, up)
    if other is None:
        return lead
    return f"{lead} {other.symbol} is going the other way, {_direction(other.gain_loss or _ZERO)}."


def _first_opposite(ranked: Sequence[Mover], up: bool) -> Mover | None:
    """The biggest mover pointing the opposite way to the lead, if any."""
    for mover in ranked:
        amount = mover.gain_loss or _ZERO
        if (amount > _ZERO) != up:
            return mover
    return None


def _direction(amount: Decimal) -> str:
    """ "up $340.00" or "down $120.00". The sign becomes a word, never a bare minus."""
    word = "up" if amount > _ZERO else "down"
    return f"{word} ${abs(amount):,.2f}"
