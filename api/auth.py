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

from dataclasses import dataclass
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


# The machine-readable marker the frontend keys off to send a signed-in but not-yet-invited
# user to the redeem-code screen. It travels in the error body's ``detail.code``.
INVITE_REQUIRED = "invite_required"


def _invite_required() -> HTTPException:
    """A 403 telling a signed-in user they still need to redeem an invite code.

    Distinct from 401 (which means "sign in again"): the token is perfectly valid, the
    person just hasn't been let into this particular app yet. ``detail`` is a small object
    so the frontend can act on ``code`` while still having a sentence to show.
    """
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": INVITE_REQUIRED,
            "message": "You need an invite code to use Stock Wizard.",
        },
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


@dataclass(frozen=True)
class AuthIdentity:
    """Who a verified token belongs to, before any database row exists for them."""

    auth_id: UUID
    email: str


def get_auth_identity(credentials: BearerDep, verifier: VerifierDep) -> AuthIdentity:
    """Verify the bearer token and return the identity it carries. No database, no provisioning.

    This is the token check on its own, so the redeem-invite route can know who is asking
    before deciding whether to open them an account. ``get_current_user`` builds on it.
    """
    if credentials is None:
        raise _unauthorized()

    claims = verifier.verify(credentials.credentials)
    try:
        auth_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    return AuthIdentity(auth_id=auth_id, email=str(claims.get("email") or ""))


def get_signup_code() -> str | None:
    """The invite code gating account creation, or None when the gate is off.

    A dependency (not a bare ``get_settings()`` read) so tests can turn the gate on and
    off without touching the process environment.
    """
    return get_settings().signup_code


def get_current_user(
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
    session: Annotated[Session, Depends(get_db)],
    signup_code: Annotated[str | None, Depends(get_signup_code)],
) -> User:
    """Resolve the verified token to a user row.

    A user who has one is returned. A user who does not is either provisioned on the spot
    (when no invite code is configured, the local-development default) or refused with a
    403 telling them to redeem a code first (when the gate is on). Provisioning past the
    gate happens only in the redeem-invite route, never here.
    """
    user = session.scalar(select(User).where(User.auth_id == identity.auth_id))
    if user is not None:
        return user
    if signup_code is not None:
        raise _invite_required()
    return get_or_create_user(session, auth_id=identity.auth_id, email=identity.email)


def get_or_create_user(session: Session, *, auth_id: UUID, email: str) -> User:
    """Find the user this token belongs to, or create the row.

    The plain provisioning helper, free of the invite gate so the redeem route and the seed
    script can both use it. Does not commit: the caller owns the transaction boundary, same
    as the sim layer.
    """
    user = session.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        user = User(auth_id=auth_id, email=email)
        session.add(user)
        session.flush()  # assigns user.id
    return user
