"""The AI tutor route and its per-account throttle.

The tutor reads only the signed-in account's money, through read-only tools scoped here. Every
figure it quotes comes from those tools (deterministic code), never the model. The throttle is
the one guard on the one route that costs us real money per call.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from auth import get_current_user, get_demo_tutor_message_limit
from config import get_settings
from models import User
from ratelimit import RateLimiter
from routers.common import BENCHMARK_SYMBOL, AccountDep, CandleDep, MarketDep, SessionDep, TutorDep
from schemas import TutorReplyOut, TutorRequest
from services.market.client import MarketError
from services.tutor.engine import Turn, run_tutor, stream_tutor
from services.tutor.provider import TutorError, TutorProvider
from services.tutor.tools import build_tools

# Keep the sent-back conversation bounded so a runaway client can't drive up cost.
MAX_TUTOR_MESSAGES = 20

# A light per-account throttle on the tutor. In-memory and per-process (see ratelimit.py),
# built from config once at startup.
_tutor_limiter = RateLimiter(max_calls=get_settings().tutor_rate_limit_per_minute, per_seconds=60)


def get_tutor_limiter() -> RateLimiter:
    """The process-wide tutor limiter. A dependency so a test can swap it out."""
    return _tutor_limiter


def enforce_tutor_rate_limit(
    account: AccountDep,
    limiter: Annotated[RateLimiter, Depends(get_tutor_limiter)],
) -> None:
    """Refuse a tutor call with 429 once an account is over its per-minute budget."""
    if not limiter.allow(str(account.id)):
        raise HTTPException(
            status_code=429,
            detail="You're asking a lot at once. Give it a minute, then try again.",
        )


# The machine-readable marker the frontend keys off to swap the tutor's composer for the
# "ask me for a full code" banner. Travels in the error body's ``detail.code``, the same shape
# the invite gate uses (see auth.py).
DEMO_LIMIT_REACHED = "demo_limit_reached"


def check_demo_tutor_allowance(
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Depends(get_demo_tutor_message_limit)],
) -> None:
    """Refuse a demo account's tutor call once it has spent its lifetime allowance.

    A courtesy check, not the guard: it answers fast and with something the UI can act on,
    but two calls racing each other could both pass it. ``_spend_tutor_message`` below is
    what actually enforces the limit. Full-tier users are never counted or checked.
    """
    if not user.is_demo:
        return
    if user.tutor_messages_used >= limit:
        raise HTTPException(
            status_code=403,
            detail={
                "code": DEMO_LIMIT_REACHED,
                "message": "That was the free question that comes with the demo code.",
            },
        )


def _spend_tutor_message(session: Session, user: User, limit: int) -> None:
    """Spend one of a demo account's tutor questions, or raise if there are none left.

    The real guard. A single conditional UPDATE, so two requests arriving together can't both
    read "0 used" and both call OpenAI: the database decides, and exactly one row updates.

    Called as late as possible, immediately before the provider call, so a request that fails
    earlier (no tutor configured, a malformed body) never costs anyone their question.
    """
    if not user.is_demo:
        return
    # Cast because Session.execute is typed as returning a plain Result, which has no
    # rowcount; an UPDATE always yields a CursorResult, which does. rowcount is the whole
    # point here: it tells us whether the WHERE matched, and so whether we won the race.
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(User)
            .where(User.id == user.id, User.tutor_messages_used < limit)
            .values(tutor_messages_used=User.tutor_messages_used + 1)
        ),
    )
    spent = result.rowcount
    session.commit()
    if not spent:
        raise HTTPException(
            status_code=403,
            detail={
                "code": DEMO_LIMIT_REACHED,
                "message": "That was the free question that comes with the demo code.",
            },
        )


def _refund_tutor_message(session: Session, user: User) -> None:
    """Give a demo user their question back when the call failed without answering.

    Only reachable on the non-streaming route, where the failure still happens inside the
    request. A stream that dies partway through has already left the request scope (and its
    session) behind, so it keeps the charge; the error copy points at a way to ask for a full
    code instead. Clamped at zero so a refund can never mint an extra question.
    """
    if not user.is_demo:
        return
    session.execute(
        update(User)
        .where(User.id == user.id, User.tutor_messages_used > 0)
        .values(tutor_messages_used=User.tutor_messages_used - 1)
    )
    session.commit()


router = APIRouter()


@router.post(
    "/api/tutor",
    dependencies=[Depends(enforce_tutor_rate_limit), Depends(check_demo_tutor_allowance)],
)
def ask_tutor(
    body: TutorRequest,
    account: AccountDep,
    session: SessionDep,
    market: MarketDep,
    candles: CandleDep,
    provider: TutorDep,
    user: Annotated[User, Depends(get_current_user)],
    demo_limit: Annotated[int, Depends(get_demo_tutor_message_limit)],
) -> TutorReplyOut:
    """Ask the AI tutor about your own portfolio, getting the whole answer back at once.

    The tutor reads only this account's money, through read-only tools scoped here to
    ``account``. Every figure it quotes comes from those tools (deterministic code), never
    from the model, and it teaches rather than advising. See services/tutor. The streaming
    variant below is what the UI uses; this one stays for a non-streaming fallback and tests.
    """
    ready = _require_ready(body, provider)
    conversation = _conversation(body)
    tools = build_tools(session, account, market, candles, benchmark_symbol=BENCHMARK_SYMBOL)
    _spend_tutor_message(session, user, demo_limit)
    try:
        answer = run_tutor(ready, tools, conversation)
    except (MarketError, TutorError) as exc:
        # The call cost nothing useful, so it shouldn't cost a demo user their question.
        _refund_tutor_message(session, user)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TutorReplyOut(reply=answer.reply)


@router.post(
    "/api/tutor/stream",
    dependencies=[Depends(enforce_tutor_rate_limit), Depends(check_demo_tutor_allowance)],
)
def ask_tutor_stream(
    body: TutorRequest,
    account: AccountDep,
    session: SessionDep,
    market: MarketDep,
    candles: CandleDep,
    provider: TutorDep,
    user: Annotated[User, Depends(get_current_user)],
    demo_limit: Annotated[int, Depends(get_demo_tutor_message_limit)],
) -> StreamingResponse:
    """Ask the AI tutor and get the reply streamed back token by token over SSE.

    Same tools, same account scoping, same "numbers from code" guard as the non-streaming route;
    only the delivery differs. Tools resolve server-side first, then the final answer streams. Each
    server-sent event is a JSON object: ``{"delta": "..."}`` for a chunk of the reply, ``{"error":
    "..."}`` if something failed mid-stream, and a final ``{"done": true}``.
    """
    ready = _require_ready(body, provider)
    conversation = _conversation(body)
    tools = build_tools(session, account, market, candles, benchmark_symbol=BENCHMARK_SYMBOL)
    # Spent here rather than inside the generator: by the time that runs the request is over
    # and its session is gone. Charging up front also means a client that hangs up mid-answer
    # still pays for the call we already made.
    _spend_tutor_message(session, user, demo_limit)

    def events() -> Iterator[str]:
        try:
            for delta in stream_tutor(ready, tools, conversation):
                yield _sse({"delta": delta})
        except (MarketError, TutorError) as exc:
            yield _sse({"error": str(exc)})
        yield _sse({"done": True})

    return StreamingResponse(events(), media_type="text/event-stream")


def _require_ready(body: TutorRequest, provider: TutorProvider | None) -> TutorProvider:
    """Confirm the tutor is configured and the request is well-formed, or raise the right error."""
    if provider is None:
        raise HTTPException(status_code=503, detail="The tutor isn't set up yet.")
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(
            status_code=400, detail="Send at least one message, ending with your question."
        )
    return provider


def _conversation(body: TutorRequest) -> list[Turn]:
    return [
        Turn(role=message.role, content=message.content)
        for message in body.messages[-MAX_TUTOR_MESSAGES:]
    ]


def _sse(payload: dict[str, object]) -> str:
    """One server-sent event carrying a JSON payload."""
    return f"data: {json.dumps(payload)}\n\n"
