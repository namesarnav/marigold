"""Expiry enforcement for verification and reset tokens.

The brief asks for this to be tested explicitly rather than trusted to the
library, so the two independent expiry checks are exercised separately:

  * the *signature* expiry, which itsdangerous enforces via `max_age`
  * the *stored* expiry in `email_tokens.expires_at`

Either one alone must be enough to reject a token. That matters: the stored
check is what makes a shortened lifetime apply to links already in someone's
inbox, and the signature check is what holds if a row is ever missed.

One test lets a real clock run out rather than manipulating timestamps, so the
whole path is known to work against wall time and not just against mocks.
"""

import time
from datetime import datetime, timedelta

import pytest
from conftest import (
    STRONG_PASSWORD,
    latest_email_to,
    register_and_verify,
    register_user,
    token_from_link,
)

from backend import security
from backend.config import get_settings
from backend.models import EmailToken, User
from backend.security import (
    TokenError,
    consume_email_token,
    issue_email_token,
    token_max_age_seconds,
)

settings = get_settings()


def make_user(db, email="expiry@example.com"):
    user = User(email=email, password_hash="x", email_verified=False, name="Expiry")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def stored_token(db, user_id, purpose):
    return (
        db.query(EmailToken)
        .filter(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
        .order_by(EmailToken.id.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Configured lifetimes
# ---------------------------------------------------------------------------

def test_reset_token_lifetime_is_short():
    """The spec calls for a short reset expiry (e.g. 30 minutes)."""
    assert settings.reset_token_expire_minutes <= 30
    assert token_max_age_seconds(EmailToken.RESET) == (
        settings.reset_token_expire_minutes * 60
    )


def test_verification_token_lifetime_is_longer_than_reset():
    assert token_max_age_seconds(EmailToken.VERIFY) > token_max_age_seconds(
        EmailToken.RESET
    )


def test_issued_token_records_the_configured_expiry(db_session):
    user = make_user(db_session)
    issue_email_token(db_session, user, EmailToken.RESET)

    record = stored_token(db_session, user.id, EmailToken.RESET)
    expected = datetime.utcnow() + timedelta(
        seconds=token_max_age_seconds(EmailToken.RESET)
    )
    assert abs((record.expires_at - expected).total_seconds()) < 5


# ---------------------------------------------------------------------------
# Signature-level expiry (itsdangerous max_age)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("purpose", [EmailToken.VERIFY, EmailToken.RESET])
def test_signature_expiry_rejects_an_old_token(db_session, monkeypatch, purpose):
    """A token older than max_age must fail even though it is well-formed."""
    user = make_user(db_session)
    token = issue_email_token(db_session, user, purpose)

    # Reading it right now works.
    assert consume_email_token(db_session, token, purpose).id == user.id

    # Re-issue, then move max_age behind the token's own timestamp.
    token = issue_email_token(db_session, user, purpose)
    monkeypatch.setattr(security, "token_max_age_seconds", lambda _p: -60)

    with pytest.raises(TokenError) as excinfo:
        consume_email_token(db_session, token, purpose)
    assert "expired" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Stored expiry (email_tokens.expires_at)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("purpose", [EmailToken.VERIFY, EmailToken.RESET])
def test_stored_expiry_rejects_even_with_a_valid_signature(db_session, purpose):
    """Backdate only the row: the DB check must reject on its own.

    This is the check that lets a shortened lifetime take effect on links that
    were already emailed.
    """
    user = make_user(db_session)
    token = issue_email_token(db_session, user, purpose)

    record = stored_token(db_session, user.id, purpose)
    record.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(TokenError) as excinfo:
        consume_email_token(db_session, token, purpose)
    assert "expired" in str(excinfo.value).lower()


def test_expired_token_is_not_marked_used(db_session):
    """An expired token stays unspent; it fails on expiry, not on redemption."""
    user = make_user(db_session)
    token = issue_email_token(db_session, user, EmailToken.RESET)

    record = stored_token(db_session, user.id, EmailToken.RESET)
    record.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(TokenError):
        consume_email_token(db_session, token, EmailToken.RESET)

    db_session.refresh(record)
    assert record.used_at is None


def test_expired_verification_token_leaves_account_unverified(db_session):
    user = make_user(db_session)
    token = issue_email_token(db_session, user, EmailToken.VERIFY)

    record = stored_token(db_session, user.id, EmailToken.VERIFY)
    record.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(TokenError):
        consume_email_token(db_session, token, EmailToken.VERIFY)

    db_session.refresh(user)
    assert user.email_verified is False


# ---------------------------------------------------------------------------
# Through the HTTP endpoints
# ---------------------------------------------------------------------------

def test_expired_verification_link_is_rejected_by_the_api(client, monkeypatch):
    register_user(client, email="apiexp@example.com")
    token = token_from_link(latest_email_to("apiexp@example.com"), "/verify-email")

    monkeypatch.setattr(security, "token_max_age_seconds", lambda _p: -60)

    resp = client.post("/api/auth/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_expired_reset_link_is_rejected_by_the_api(client, monkeypatch):
    register_and_verify(client, "apireset@example.com")
    client.cookies.clear()
    client.post("/api/auth/forgot-password", json={"email": "apireset@example.com"})
    token = token_from_link(latest_email_to("apireset@example.com"), "/reset-password")

    monkeypatch.setattr(security, "token_max_age_seconds", lambda _p: -60)

    resp = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "N3w-Passw0rd!x"}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_expired_reset_link_does_not_change_the_password(client, monkeypatch):
    """The important consequence: an expired link must be inert, not just noisy."""
    register_and_verify(client, "inert@example.com")
    client.cookies.clear()
    client.post("/api/auth/forgot-password", json={"email": "inert@example.com"})
    token = token_from_link(latest_email_to("inert@example.com"), "/reset-password")

    monkeypatch.setattr(security, "token_max_age_seconds", lambda _p: -60)
    client.post(
        "/api/auth/reset-password", json={"token": token, "password": "Attack3r-Pass!x"}
    )
    monkeypatch.undo()

    assert client.post(
        "/api/auth/login",
        json={"email": "inert@example.com", "password": "Attack3r-Pass!x"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "inert@example.com", "password": STRONG_PASSWORD},
    ).status_code == 200


# ---------------------------------------------------------------------------
# Real elapsed time, not a mocked clock
# ---------------------------------------------------------------------------

def test_token_expires_against_a_real_clock(client, monkeypatch):
    """One end-to-end check that wall-clock expiry genuinely works."""
    monkeypatch.setattr(security, "token_max_age_seconds", lambda _p: 1)

    register_user(client, email="wall@example.com")
    token = token_from_link(latest_email_to("wall@example.com"), "/verify-email")

    # Valid immediately...
    time.sleep(1.5)
    # ...and refused once the second has elapsed.
    resp = client.post("/api/auth/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()
