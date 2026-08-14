"""The AI tutor route and its per-account throttle.

The tutor reads only the signed-in account's money, through read-only tools scoped here. Every
figure it quotes comes from those tools (deterministic code), never the model. The throttle is
the one guard on the one route that costs us real money per call.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from config import get_settings
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


router = APIRouter()


@router.post("/api/tutor", dependencies=[Depends(enforce_tutor_rate_limit)])
def ask_tutor(
    body: TutorRequest,
    account: AccountDep,
    session: SessionDep,
    market: MarketDep,
    candles: CandleDep,
    provider: TutorDep,
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
    try:
        answer = run_tutor(ready, tools, conversation)
    except (MarketError, TutorError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TutorReplyOut(reply=answer.reply)


@router.post("/api/tutor/stream", dependencies=[Depends(enforce_tutor_rate_limit)])
def ask_tutor_stream(
    body: TutorRequest,
    account: AccountDep,
    session: SessionDep,
    market: MarketDep,
    candles: CandleDep,
    provider: TutorDep,
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
