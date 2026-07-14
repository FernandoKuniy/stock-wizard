"""Tests for Supabase access-token verification.

These sign real ES256 tokens with a throwaway key and hand the verifier the matching
public key, so the actual signature, expiry, issuer, and audience checks all run. The
only thing stubbed out is the network fetch of the project's JWKS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import AUDIENCE, TokenVerifier, get_or_create_user
from models import User

ISSUER = "https://test-project.supabase.co/auth/v1"


@pytest.fixture(scope="module")
def signing_key() -> ec.EllipticCurvePrivateKey:
    """A throwaway P-256 key standing in for the project's Supabase signing key."""
    return ec.generate_private_key(ec.SECP256R1())


class StubKeys:
    """Stands in for PyJWKClient: hands back one public key, no network."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._public_key)


@pytest.fixture
def verifier(signing_key: ec.EllipticCurvePrivateKey) -> TokenVerifier:
    return TokenVerifier(
        jwks_url="https://test-project.supabase.co/unused",
        issuer=ISSUER,
        keys=StubKeys(signing_key.public_key()),
    )


def make_token(
    signing_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str | None = None,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_in: timedelta = timedelta(hours=1),
    email: str = "learner@example.com",
) -> str:
    """Sign an access token shaped like the ones Supabase issues."""
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "exp": now + expires_in,
        "iat": now,
        "email": email,
    }
    if sub is not None:
        claims["sub"] = sub
    return jwt.encode(claims, signing_key, algorithm="ES256")


def test_valid_token_returns_its_claims(
    verifier: TokenVerifier, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    sub = str(uuid4())
    claims = verifier.verify(make_token(signing_key, sub=sub))

    assert claims["sub"] == sub
    assert claims["email"] == "learner@example.com"


def test_expired_token_is_rejected(
    verifier: TokenVerifier, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    token = make_token(signing_key, sub=str(uuid4()), expires_in=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc:
        verifier.verify(token)
    assert exc.value.status_code == 401


def test_token_from_another_project_is_rejected(
    verifier: TokenVerifier, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    token = make_token(signing_key, sub=str(uuid4()), issuer="https://evil.supabase.co/auth/v1")

    with pytest.raises(HTTPException) as exc:
        verifier.verify(token)
    assert exc.value.status_code == 401


def test_token_with_the_wrong_audience_is_rejected(
    verifier: TokenVerifier, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    token = make_token(signing_key, sub=str(uuid4()), audience="anon")

    with pytest.raises(HTTPException) as exc:
        verifier.verify(token)
    assert exc.value.status_code == 401


def test_token_signed_by_a_different_key_is_rejected(verifier: TokenVerifier) -> None:
    # The signature is well-formed, but not by the key the project publishes.
    impostor = ec.generate_private_key(ec.SECP256R1())
    token = make_token(impostor, sub=str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        verifier.verify(token)
    assert exc.value.status_code == 401


def test_token_without_a_subject_is_rejected(
    verifier: TokenVerifier, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(HTTPException) as exc:
        verifier.verify(make_token(signing_key, sub=None))
    assert exc.value.status_code == 401


def test_garbage_is_rejected(verifier: TokenVerifier) -> None:
    with pytest.raises(HTTPException) as exc:
        verifier.verify("not-a-jwt")
    assert exc.value.status_code == 401


def test_get_or_create_user_is_idempotent(db_session: Session) -> None:
    auth_id = uuid4()

    first = get_or_create_user(db_session, auth_id=auth_id, email="learner@example.com")
    db_session.commit()
    second = get_or_create_user(db_session, auth_id=auth_id, email="learner@example.com")
    db_session.commit()

    assert first.id == second.id
    assert len(db_session.scalars(select(User)).all()) == 1


def test_different_subjects_are_different_users(db_session: Session) -> None:
    one = get_or_create_user(db_session, auth_id=uuid4(), email="a@example.com")
    two = get_or_create_user(db_session, auth_id=uuid4(), email="b@example.com")
    db_session.commit()

    assert one.id != two.id
    assert len(db_session.scalars(select(User)).all()) == 2
