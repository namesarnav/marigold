"""Integration tests for /api/auth/* endpoints."""

from conftest import (
    STRONG_PASSWORD,
    latest_email_to,
    register_and_verify,
    register_user,
    token_from_link,
    verify_user,
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_success(client):
    resp = register_user(client, email="new@example.com", name="New User")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # A brand-new password account starts unverified.
    assert data["email_verified"] is False
    assert data["user"]["auth_methods"] == ["password"]


def test_register_duplicate_email(client):
    register_user(client, email="dup@example.com", name="Dup")
    resp = register_user(client, email="dup@example.com", name="Dup")
    assert resp.status_code == 409


def test_register_invalid_email(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": STRONG_PASSWORD, "name": "Bad"},
    )
    assert resp.status_code == 422


def test_register_normalizes_email_case(client):
    assert register_user(client, email="Mixed@Example.COM").status_code == 200
    # The lowercased form must collide, or two accounts could own one address.
    assert register_user(client, email="mixed@example.com").status_code == 409


def test_register_sends_verification_email(client):
    register_user(client, email="mail@example.com")
    message = latest_email_to("mail@example.com")
    assert message is not None
    assert "/verify-email?token=" in message.text_body


# ---------------------------------------------------------------------------
# Password strength (server-side; the frontend rule does not count)
# ---------------------------------------------------------------------------

def test_register_rejects_short_password(client):
    resp = register_user(client, email="s@example.com", password="Ab3!x")
    assert resp.status_code == 422
    assert "12 characters" in resp.json()["detail"]


def test_register_rejects_common_password(client):
    resp = register_user(client, email="c@example.com", password="Password123!")
    assert resp.status_code == 422
    assert "too common" in resp.json()["detail"].lower()


def test_register_rejects_single_character_class(client):
    resp = register_user(client, email="l@example.com", password="abcdefghijklmnop")
    assert resp.status_code == 422
    assert "three of" in resp.json()["detail"]


def test_register_rejects_password_containing_email(client):
    resp = register_user(
        client, email="jflanders@example.com", password="Jflanders-99!x"
    )
    assert resp.status_code == 422
    assert "name or email" in resp.json()["detail"]


def test_register_rejects_overlong_password(client):
    # Longer than bcrypt's 72-byte input limit: must be rejected, not truncated.
    resp = register_user(client, email="o@example.com", password="Aa1!" + "x" * 200)
    assert resp.status_code == 422


def test_register_accepts_strong_password(client):
    assert register_user(client, email="ok@example.com").status_code == 200


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success(client):
    register_user(client, email="login@example.com", name="Login")
    resp = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": STRONG_PASSWORD},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    register_user(client, email="wp@example.com", name="WP")
    resp = client.post(
        "/api/auth/login", json={"email": "wp@example.com", "password": "Wr0ng-Pass!99"}
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "Anything-Here!1"},
    )
    assert resp.status_code == 401


def test_login_error_does_not_reveal_which_field_was_wrong(client):
    """Unknown address and wrong password must be indistinguishable."""
    register_user(client, email="enum@example.com")

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "enum@example.com", "password": "Wr0ng-Pass!99"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "Wr0ng-Pass!99"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]
    detail = wrong_password.json()["detail"].lower()
    assert "email" in detail and "password" in detail
    # Must not name the failing field.
    assert "not found" not in detail
    assert "incorrect password" not in detail


def test_unverified_user_can_still_log_in(client):
    """Verification gates features, not authentication itself.

    An unverified user has to be able to authenticate, or they could never
    reach the resend-verification flow.
    """
    register_user(client, email="unv@example.com")
    resp = client.post(
        "/api/auth/login",
        json={"email": "unv@example.com", "password": STRONG_PASSWORD},
    )
    assert resp.status_code == 200
    assert resp.json()["email_verified"] is False


# ---------------------------------------------------------------------------
# Session mechanics (unchanged by the upgrade)
# ---------------------------------------------------------------------------

def test_refresh_after_login(client):
    register_user(client, email="rf@example.com", name="RF")
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_without_cookie(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_logout_success(client):
    register_user(client, email="lo@example.com", name="LO")
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out"


def test_me_authenticated(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "tester@example.com"
    assert data["name"] == "Tester"
    assert data["email_verified"] is True
    assert "id" in data


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert resp.status_code == 401


def test_me_works_for_unverified_user(client, unverified_auth_headers):
    """`/me` stays open so the UI can render the interstitial."""
    resp = client.get("/api/auth/me", headers=unverified_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email_verified"] is False


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def test_verify_email_marks_account_verified(client):
    register_user(client, email="v@example.com")
    token = verify_user(client, "v@example.com")
    assert token

    client.cookies.clear()
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email_verified"] is True


def test_verify_email_rejects_garbage_token(client):
    resp = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400


def test_verification_token_is_single_use(client):
    """A link that has been spent must not work a second time."""
    register_user(client, email="once@example.com")
    message = latest_email_to("once@example.com")
    token = token_from_link(message, "/verify-email")

    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    second = client.post("/api/auth/verify-email", json={"token": token})
    assert second.status_code == 400
    assert "already been used" in second.json()["detail"]


def test_resending_verification_invalidates_the_previous_link(client):
    """Only the newest link may work, so an intercepted older one is dead."""
    register_user(client, email="rot@example.com")
    first = token_from_link(latest_email_to("rot@example.com"), "/verify-email")

    client.post("/api/auth/resend-verification", json={"email": "rot@example.com"})
    second = token_from_link(latest_email_to("rot@example.com"), "/verify-email")
    assert first != second

    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_verification_does_not_leak_account_existence(client):
    register_user(client, email="real@example.com")
    known = client.post("/api/auth/resend-verification", json={"email": "real@example.com"})
    unknown = client.post(
        "/api/auth/resend-verification", json={"email": "ghost@example.com"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_resend_verification_sends_nothing_for_verified_account(client):
    from backend.mailer import SENT_EMAILS

    register_and_verify(client, "done@example.com")
    SENT_EMAILS.clear()

    resp = client.post("/api/auth/resend-verification", json={"email": "done@example.com"})
    assert resp.status_code == 200
    assert latest_email_to("done@example.com") is None


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def test_password_reset_end_to_end(client):
    register_and_verify(client, "reset@example.com")
    client.cookies.clear()

    assert client.post(
        "/api/auth/forgot-password", json={"email": "reset@example.com"}
    ).status_code == 200

    token = token_from_link(latest_email_to("reset@example.com"), "/reset-password")
    new_password = "N3w-Passw0rd!x"
    resp = client.post(
        "/api/auth/reset-password", json={"token": token, "password": new_password}
    )
    assert resp.status_code == 200

    # Old password no longer works, new one does.
    assert client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": STRONG_PASSWORD},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": new_password},
    ).status_code == 200


def test_forgot_password_does_not_leak_account_existence(client):
    register_and_verify(client, "known@example.com")
    known = client.post("/api/auth/forgot-password", json={"email": "known@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "no@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_token_is_single_use(client):
    register_and_verify(client, "single@example.com")
    client.post("/api/auth/forgot-password", json={"email": "single@example.com"})
    token = token_from_link(latest_email_to("single@example.com"), "/reset-password")

    first = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "F1rst-Reset!xy"}
    )
    assert first.status_code == 200

    second = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "Sec0nd-Reset!xy"}
    )
    assert second.status_code == 400
    assert "already been used" in second.json()["detail"]

    # The second attempt must not have taken effect.
    assert client.post(
        "/api/auth/login",
        json={"email": "single@example.com", "password": "Sec0nd-Reset!xy"},
    ).status_code == 401


def test_reset_password_enforces_strength(client):
    register_and_verify(client, "weak@example.com")
    client.post("/api/auth/forgot-password", json={"email": "weak@example.com"})
    token = token_from_link(latest_email_to("weak@example.com"), "/reset-password")

    resp = client.post("/api/auth/reset-password", json={"token": token, "password": "short"})
    assert resp.status_code == 422


def test_reset_password_revokes_existing_sessions(client):
    """A session an attacker already holds must not survive the reset."""
    # Not register_and_verify: that clears cookies, and this test needs the
    # live refresh cookie the flow hands out.
    register_user(client, email="revoke@example.com")
    verify_user(client, "revoke@example.com")
    assert client.post("/api/auth/refresh").status_code == 200

    client.post("/api/auth/forgot-password", json={"email": "revoke@example.com"})
    token = token_from_link(latest_email_to("revoke@example.com"), "/reset-password")
    client.post(
        "/api/auth/reset-password", json={"token": token, "password": "Rev0ked-Pass!x"}
    )

    assert client.post("/api/auth/refresh").status_code == 401


def test_verification_token_cannot_be_used_as_reset_token(client):
    """Different signing salts keep the two token families separate."""
    register_user(client, email="cross@example.com")
    verify_token = token_from_link(latest_email_to("cross@example.com"), "/verify-email")

    resp = client.post(
        "/api/auth/reset-password",
        json={"token": verify_token, "password": "Cr0ss-Purpose!x"},
    )
    assert resp.status_code == 400


def test_bearer_token_wins_over_a_stale_session_cookie(client):
    """An explicit Authorization header must beat an ambient session cookie.

    Regression test. `get_current_user` used to resolve the session cookie
    first, so a client holding a cookie for one account was resolved as that
    account even when it presented a valid bearer token for another. On a shared
    browser or after an OAuth login that is one user reading another user's
    data, so the ordering is pinned here rather than left implicit.
    """
    # Register A, then B. The TestClient keeps B's session cookie, because it is
    # the most recent registration and cookies persist across requests.
    register_user(client, email="alice@example.com", name="Alice")
    alice_token = verify_user(client, "alice@example.com")

    register_user(client, email="bob@example.com", name="Bob")
    verify_user(client, "bob@example.com")

    assert client.cookies, "precondition: the client should be holding Bob's cookie"

    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {alice_token}"}
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "alice@example.com"


def test_session_cookie_still_authenticates_when_no_header_is_sent(client):
    """The cookie fallback must survive the reordering — OAuth logins rely on it."""
    register_user(client, email="cookie@example.com", name="Cookie")
    verify_user(client, "cookie@example.com")

    me = client.get("/api/auth/me")  # no Authorization header at all
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "cookie@example.com"
