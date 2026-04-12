"""Rate-limiting behaviour on login and resend-verification.

These drive the real endpoints rather than the limiter in isolation, because
the thing worth protecting is the endpoint: the interesting bugs are counting
successes, forgetting to reset on success, or keying the counter so that
casing variants each get a fresh budget.

The suite runs against the in-process limiter backend (no REDIS_URL in
conftest). The counting logic is backend-agnostic; the Redis backend differs
only in where the integer lives.
"""

import pytest
from conftest import STRONG_PASSWORD, register_and_verify, register_user

from backend.config import get_settings
from backend.ratelimit import (
    RateLimiter,
    _MemoryBackend,
    get_limiter,
    login_account_key,
    resend_verification_key,
)

settings = get_settings()

WRONG = "Wr0ng-Password!99"


def attempt_login(client, email, password=WRONG):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture()
def tight_limits(monkeypatch):
    """Small, explicit budgets so tests state their own thresholds."""
    monkeypatch.setattr(settings, "login_max_attempts_per_account", 3)
    monkeypatch.setattr(settings, "login_max_attempts_per_ip", 50)
    monkeypatch.setattr(settings, "login_attempt_window_seconds", 900)
    yield


# ---------------------------------------------------------------------------
# Login — per account
# ---------------------------------------------------------------------------

def test_login_locks_out_after_too_many_failures(client, tight_limits):
    register_user(client, email="brute@example.com")

    for _ in range(3):
        assert attempt_login(client, "brute@example.com").status_code == 401

    blocked = attempt_login(client, "brute@example.com")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_lockout_blocks_even_the_correct_password(client, tight_limits):
    """Otherwise the limit would be trivially bypassable by guessing correctly."""
    register_and_verify(client, "brute2@example.com")
    client.cookies.clear()

    for _ in range(3):
        attempt_login(client, "brute2@example.com")

    resp = attempt_login(client, "brute2@example.com", password=STRONG_PASSWORD)
    assert resp.status_code == 429


def test_successful_login_resets_the_counter(client, tight_limits):
    """Only failures count, so ordinary users never lock themselves out."""
    register_and_verify(client, "ok@example.com")
    client.cookies.clear()

    # Two failures, then a success clears the budget.
    attempt_login(client, "ok@example.com")
    attempt_login(client, "ok@example.com")
    assert attempt_login(client, "ok@example.com", password=STRONG_PASSWORD).status_code == 200

    # A full fresh budget is available again.
    for _ in range(3):
        assert attempt_login(client, "ok@example.com").status_code == 401
    assert attempt_login(client, "ok@example.com").status_code == 429


def test_lockout_is_per_account_not_global(client, tight_limits):
    """One account being throttled must not lock everyone else out."""
    register_and_verify(client, "victim@example.com")
    register_and_verify(client, "bystander@example.com")
    client.cookies.clear()

    for _ in range(4):
        attempt_login(client, "victim@example.com")
    assert attempt_login(client, "victim@example.com").status_code == 429

    assert attempt_login(
        client, "bystander@example.com", password=STRONG_PASSWORD
    ).status_code == 200


def test_unknown_email_is_rate_limited_too(client, tight_limits):
    """Or the limiter itself would leak which addresses exist."""
    for _ in range(3):
        assert attempt_login(client, "ghost@example.com").status_code == 401
    assert attempt_login(client, "ghost@example.com").status_code == 429


def test_casing_variants_share_one_budget(client, tight_limits):
    """Otherwise an attacker gets a fresh allowance per capitalisation."""
    register_user(client, email="case@example.com")

    attempt_login(client, "case@example.com")
    attempt_login(client, "CASE@example.com")
    attempt_login(client, "Case@Example.COM")

    assert attempt_login(client, "case@example.com").status_code == 429


# ---------------------------------------------------------------------------
# Login — per IP
# ---------------------------------------------------------------------------

def test_login_is_limited_per_ip_across_accounts(client, monkeypatch):
    """Spraying one guess across many accounts must still hit a ceiling."""
    monkeypatch.setattr(settings, "login_max_attempts_per_account", 100)
    monkeypatch.setattr(settings, "login_max_attempts_per_ip", 5)

    for i in range(5):
        assert attempt_login(client, f"spray{i}@example.com").status_code == 401

    # Sixth distinct account from the same IP: still blocked.
    assert attempt_login(client, "spray-last@example.com").status_code == 429


def test_per_ip_limit_uses_forwarded_header(client, monkeypatch):
    """Behind the ingress the real client IP arrives in X-Forwarded-For."""
    monkeypatch.setattr(settings, "login_max_attempts_per_account", 100)
    monkeypatch.setattr(settings, "login_max_attempts_per_ip", 2)

    for _ in range(2):
        client.post(
            "/api/auth/login",
            json={"email": "a@example.com", "password": WRONG},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
    blocked = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": WRONG},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert blocked.status_code == 429

    # A different forwarded IP has its own budget.
    other = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": WRONG},
        headers={"X-Forwarded-For": "198.51.100.4"},
    )
    assert other.status_code == 401


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

def test_resend_verification_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "resend_verification_max_per_hour", 2)
    register_user(client, email="spam@example.com")

    for _ in range(2):
        assert client.post(
            "/api/auth/resend-verification", json={"email": "spam@example.com"}
        ).status_code == 200

    blocked = client.post(
        "/api/auth/resend-verification", json={"email": "spam@example.com"}
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_resend_limit_stops_further_emails(client, monkeypatch):
    """The point of the limit is that no more mail goes out."""
    from backend.mailer import SENT_EMAILS

    monkeypatch.setattr(settings, "resend_verification_max_per_hour", 2)
    register_user(client, email="count@example.com")
    SENT_EMAILS.clear()

    for _ in range(6):
        client.post("/api/auth/resend-verification", json={"email": "count@example.com"})

    assert len(SENT_EMAILS) == 2


def test_resend_limit_applies_to_unknown_addresses(client, monkeypatch):
    """Otherwise the 429 boundary would itself reveal which accounts exist."""
    monkeypatch.setattr(settings, "resend_verification_max_per_hour", 2)

    for _ in range(2):
        assert client.post(
            "/api/auth/resend-verification", json={"email": "nobody@example.com"}
        ).status_code == 200
    assert client.post(
        "/api/auth/resend-verification", json={"email": "nobody@example.com"}
    ).status_code == 429


def test_resend_limit_is_per_address(client, monkeypatch):
    monkeypatch.setattr(settings, "resend_verification_max_per_hour", 1)
    register_user(client, email="one@example.com")
    register_user(client, email="two@example.com")

    assert client.post(
        "/api/auth/resend-verification", json={"email": "one@example.com"}
    ).status_code == 200
    assert client.post(
        "/api/auth/resend-verification", json={"email": "one@example.com"}
    ).status_code == 429
    # A different address still has its own budget.
    assert client.post(
        "/api/auth/resend-verification", json={"email": "two@example.com"}
    ).status_code == 200


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

def test_forgot_password_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "password_reset_max_per_hour", 2)
    register_and_verify(client, "reset-spam@example.com")

    for _ in range(2):
        assert client.post(
            "/api/auth/forgot-password", json={"email": "reset-spam@example.com"}
        ).status_code == 200
    assert client.post(
        "/api/auth/forgot-password", json={"email": "reset-spam@example.com"}
    ).status_code == 429


# ---------------------------------------------------------------------------
# Limiter mechanics
# ---------------------------------------------------------------------------

def test_window_expiry_restores_the_budget():
    """The window must actually expire rather than latching permanently."""
    limiter = RateLimiter(_MemoryBackend())

    # A zero-length window is expired by the time the next call reads it.
    for _ in range(5):
        limiter.hit("k", limit=1, window_seconds=0)
    assert limiter.hit("k", limit=1, window_seconds=0).allowed is True


def test_hit_reports_remaining_and_retry_after():
    limiter = RateLimiter(_MemoryBackend())
    first = limiter.hit("k", limit=2, window_seconds=60)
    assert first.allowed is True and first.remaining == 1

    second = limiter.hit("k", limit=2, window_seconds=60)
    assert second.allowed is True and second.remaining == 0

    third = limiter.hit("k", limit=2, window_seconds=60)
    assert third.allowed is False
    assert third.remaining == 0
    assert third.retry_after_seconds > 0


def test_reset_clears_a_single_key():
    limiter = RateLimiter(_MemoryBackend())
    limiter.hit("a", limit=1, window_seconds=60)
    limiter.hit("b", limit=1, window_seconds=60)

    limiter.reset("a")
    assert limiter.peek_blocked("a", limit=1) is False
    assert limiter.peek_blocked("b", limit=1) is True


def test_peek_does_not_consume_budget():
    limiter = RateLimiter(_MemoryBackend())
    for _ in range(10):
        assert limiter.peek_blocked("k", limit=1) is False
    assert limiter.hit("k", limit=1, window_seconds=60).allowed is True


def test_key_builders_normalize_email_case():
    assert login_account_key("A@B.com") == login_account_key("a@b.com")
    assert resend_verification_key(" A@B.com ") == resend_verification_key("a@b.com")


def test_default_backend_is_memory_without_redis_url():
    """conftest sets no REDIS_URL, so the suite must be on the fallback."""
    assert get_limiter().backend_name == "memory"
