"""Supabase Auth: turning a bearer token into the user who sent it.

The frontend signs people in with Supabase Auth and sends the resulting access
token on every call. We verify that token here, locally, against the project's
public JWKS. The tokens are signed with an asymmetric key (ES256), so the API
holds no shared secret and never has to call Supabase to check a request.

IMPORTANT: our tables are read over a direct Postgres connection, not through
PostgREST, so Supabase Row Level Security does NOT protect them. Authorization is
enforced here instead: a request is resolved to one user, and every query is scoped
to that user's account. See docs/architecture.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Protocol
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from models import User

# Supabase stamps every signed-in user's token with this audience.
AUDIENCE = "authenticated"
# Asymmetric algorithms only. HS256 (the legacy shared secret) is deliberately not
# accepted, so no leaked secret can mint a token this API would trust.
ALGORITHMS = ["ES256", "RS256"]


def _unauthorized() -> HTTPException:
    """A 401 that says the same thing no matter why the token failed."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to continue.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class SigningKeyResolver(Protocol):
    """The slice of PyJWKClient we use: find the key that signed this token."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class TokenVerifier:
    """Verifies Supabase access tokens against the project's published public keys."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        keys: SigningKeyResolver | None = None,
    ) -> None:
        # PyJWKClient caches the key set, so verifying a token is not a network call.
        self._keys = keys or jwt.PyJWKClient(jwks_url, cache_keys=True)
        self._issuer = issuer

    def verify(self, token: str) -> dict[str, Any]:
        """Return the token's claims, or raise 401 if it isn't a live token from our project."""
        try:
            key = self._keys.get_signing_key_from_jwt(token).key
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            # Covers a bad signature, an expired token, a wrong issuer or audience,
            # and a JWKS we could not fetch. The user just needs to sign in again.
            raise _unauthorized() from exc
        return claims


@lru_cache
def get_token_verifier() -> TokenVerifier:
    """Return the process-wide verifier (it caches the project's public keys)."""
    settings = get_settings()
    return TokenVerifier(
        jwks_url=settings.supabase_jwks_url,
        issuer=settings.supabase_issuer,
    )


_bearer = HTTPBearer(auto_error=False)

BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
VerifierDep = Annotated[TokenVerifier, Depends(get_token_verifier)]


def get_current_user(
    credentials: BearerDep,
    verifier: VerifierDep,
    session: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the bearer token to a user row, creating it the first time they sign in."""
    if credentials is None:
        raise _unauthorized()

    claims = verifier.verify(credentials.credentials)
    try:
        auth_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    return get_or_create_user(session, auth_id=auth_id, email=str(claims.get("email") or ""))


def get_or_create_user(session: Session, *, auth_id: UUID, email: str) -> User:
    """Find the user this token belongs to, or create the row on first sign-in.

    Does not commit: the caller owns the transaction boundary, same as the sim layer.
    """
    user = session.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        user = User(auth_id=auth_id, email=email)
        session.add(user)
        session.flush()  # assigns user.id
    return user
