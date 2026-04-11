"""Account-linking tests for OAuth sign-in.

This is the highest-risk logic in the auth upgrade: a mistake here is an
account-takeover bug, not a broken feature. The tests drive
`resolve_oauth_login` directly, because it is the whole decision — the HTTP
callback around it only fetches the profile and sets cookies.

The three cases from the spec:
  1. OAuth email matches a VERIFIED account   -> link, do not duplicate
  2. OAuth email matches an UNVERIFIED account -> refuse, surface a conflict
  3. No matching account                       -> create, pre-verified
"""

import pytest
from conftest import STRONG_PASSWORD, register_and_verify, register_user

from backend.models import AuthProvider, User
from backend.oauth import (
    AccountConflictError,
    OAuthError,
    ProviderProfile,
    profile_from_github,
    profile_from_google,
    resolve_oauth_login,
)
from backend.security import hash_password


def google_profile(email="user@example.com", sub="google-sub-1", name="Test User",
                   verified=True):
    return ProviderProfile(
        provider=AuthProvider.GOOGLE,
        provider_user_id=sub,
        email=email,
        email_verified=verified,
        name=name,
    )


def github_profile(email="user@example.com", uid="github-123", name="Test User",
                   verified=True):
    return ProviderProfile(
        provider=AuthProvider.GITHUB,
        provider_user_id=uid,
        email=email,
        email_verified=verified,
        name=name,
    )


def make_user(db, email, *, verified, with_password=True, name="Existing"):
    user = User(
        email=email,
        password_hash=hash_password(STRONG_PASSWORD) if with_password else None,
        email_verified=verified,
        name=name,
    )
    db.add(user)
    db.flush()
    if with_password:
        db.add(
            AuthProvider(
                user_id=user.id, provider=AuthProvider.PASSWORD, provider_user_id=None
            )
        )
    db.commit()
    db.refresh(user)
    return user


def methods_of(db, user):
    return sorted(
        r[0]
        for r in db.query(AuthProvider.provider)
        .filter(AuthProvider.user_id == user.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Case 3 — no existing account
# ---------------------------------------------------------------------------

def test_new_oauth_user_is_created_pre_verified(db_session):
    user, created = resolve_oauth_login(db_session, google_profile())

    assert created is True
    assert user.email == "user@example.com"
    # Trusting the provider's verification, per the spec.
    assert user.email_verified is True
    # OAuth-only account: no password, and none should be invented.
    assert user.password_hash is None
    assert methods_of(db_session, user) == ["google"]


def test_new_oauth_user_creates_exactly_one_user_row(db_session):
    resolve_oauth_login(db_session, google_profile())
    assert db_session.query(User).filter(User.email == "user@example.com").count() == 1


def test_oauth_signup_sends_no_verification_email(db_session):
    """OAuth accounts are pre-verified, so no confirmation mail goes out."""
    from backend.mailer import SENT_EMAILS

    SENT_EMAILS.clear()
    resolve_oauth_login(db_session, google_profile(email="fresh@example.com"))
    assert SENT_EMAILS == []


# ---------------------------------------------------------------------------
# Case 1 — existing VERIFIED account: link, never duplicate
# ---------------------------------------------------------------------------

def test_links_to_existing_verified_account(db_session):
    existing = make_user(db_session, "verified@example.com", verified=True)

    user, created = resolve_oauth_login(
        db_session, google_profile(email="verified@example.com")
    )

    assert created is False
    assert user.id == existing.id
    # Password survives: the account now has both ways in.
    assert user.password_hash is not None
    assert methods_of(db_session, user) == ["google", "password"]
    assert db_session.query(User).count() == 1


def test_can_link_both_providers_to_one_account(db_session):
    """Spec Phase 1: password AND several OAuth providers simultaneously."""
    existing = make_user(db_session, "multi@example.com", verified=True)

    resolve_oauth_login(db_session, google_profile(email="multi@example.com"))
    user, _ = resolve_oauth_login(db_session, github_profile(email="multi@example.com"))

    assert user.id == existing.id
    assert methods_of(db_session, user) == ["github", "google", "password"]
    assert db_session.query(User).count() == 1


def test_linking_is_case_insensitive_on_email(db_session):
    """A provider returning different casing must not create a second account."""
    existing = make_user(db_session, "casing@example.com", verified=True)

    user, created = resolve_oauth_login(
        db_session, google_profile(email="Casing@Example.COM")
    )

    assert created is False
    assert user.id == existing.id
    assert db_session.query(User).count() == 1


def test_linking_backfills_a_missing_name(db_session):
    existing = make_user(db_session, "noname@example.com", verified=True, name=None)
    user, _ = resolve_oauth_login(
        db_session, google_profile(email="noname@example.com", name="From Google")
    )
    assert user.name == "From Google"


def test_linking_does_not_overwrite_an_existing_name(db_session):
    make_user(db_session, "named@example.com", verified=True, name="Chosen Name")
    user, _ = resolve_oauth_login(
        db_session, google_profile(email="named@example.com", name="From Google")
    )
    assert user.name == "Chosen Name"


# ---------------------------------------------------------------------------
# Case 2 — existing UNVERIFIED account: refuse. This is the takeover case.
# ---------------------------------------------------------------------------

def test_oauth_refuses_to_take_over_unverified_account(db_session):
    existing = make_user(db_session, "pending@example.com", verified=False)

    with pytest.raises(AccountConflictError) as excinfo:
        resolve_oauth_login(db_session, google_profile(email="pending@example.com"))

    assert excinfo.value.email == "pending@example.com"
    assert "not been verified" in excinfo.value.message

    db_session.refresh(existing)
    # Nothing may have changed: no link, still unverified, still password-only.
    assert existing.email_verified is False
    assert methods_of(db_session, existing) == ["password"]
    assert db_session.query(AuthProvider).filter(
        AuthProvider.provider == AuthProvider.GOOGLE
    ).count() == 0


def test_unverified_conflict_does_not_create_a_duplicate_user(db_session):
    make_user(db_session, "pending2@example.com", verified=False)
    with pytest.raises(AccountConflictError):
        resolve_oauth_login(db_session, github_profile(email="pending2@example.com"))
    assert db_session.query(User).count() == 1


def test_oauth_login_works_after_the_account_verifies(db_session):
    """The documented way out of the conflict: verify first, then link."""
    existing = make_user(db_session, "later@example.com", verified=False)

    with pytest.raises(AccountConflictError):
        resolve_oauth_login(db_session, google_profile(email="later@example.com"))

    existing.email_verified = True
    db_session.commit()

    user, created = resolve_oauth_login(
        db_session, google_profile(email="later@example.com")
    )
    assert created is False
    assert user.id == existing.id
    assert methods_of(db_session, user) == ["google", "password"]


def test_conflict_is_surfaced_through_the_full_signup_flow(client, db_session):
    """End to end: register by password, don't verify, then try OAuth."""
    register_user(client, email="flow@example.com", name="Flow")

    with pytest.raises(AccountConflictError):
        resolve_oauth_login(db_session, google_profile(email="flow@example.com"))


# ---------------------------------------------------------------------------
# Case 0 — returning user, matched on provider subject id
# ---------------------------------------------------------------------------

def test_returning_oauth_user_matches_on_provider_id(db_session):
    first, _ = resolve_oauth_login(db_session, google_profile(sub="stable-sub"))
    second, created = resolve_oauth_login(db_session, google_profile(sub="stable-sub"))

    assert created is False
    assert second.id == first.id
    assert db_session.query(User).count() == 1


def test_returning_user_matched_by_id_even_after_changing_provider_email(db_session):
    """Provider subject id is the identity; the email is just an attribute."""
    first, _ = resolve_oauth_login(
        db_session, google_profile(email="old@example.com", sub="stable-sub")
    )
    second, created = resolve_oauth_login(
        db_session, google_profile(email="new@example.com", sub="stable-sub")
    )

    assert created is False
    assert second.id == first.id
    assert db_session.query(User).count() == 1


def test_same_email_different_provider_ids_do_not_collide(db_session):
    """Google and GitHub subject ids live in separate namespaces."""
    user_a, _ = resolve_oauth_login(
        db_session, google_profile(email="both@example.com", sub="1")
    )
    user_b, _ = resolve_oauth_login(
        db_session, github_profile(email="both@example.com", uid="1")
    )
    # Same account, reached twice — not two accounts, and not a mismatch.
    assert user_a.id == user_b.id
    assert methods_of(db_session, user_a) == ["github", "google"]


# ---------------------------------------------------------------------------
# Unverified provider emails must never be trusted
# ---------------------------------------------------------------------------

def test_unverified_provider_email_is_rejected(db_session):
    """A provider address the provider itself has not verified proves nothing."""
    with pytest.raises(OAuthError):
        resolve_oauth_login(db_session, google_profile(verified=False))
    assert db_session.query(User).count() == 0


def test_unverified_provider_email_cannot_reach_a_verified_account(db_session):
    """The takeover attempt this guard exists to stop."""
    make_user(db_session, "victim@example.com", verified=True)

    with pytest.raises(OAuthError):
        resolve_oauth_login(
            db_session, google_profile(email="victim@example.com", verified=False)
        )

    assert db_session.query(AuthProvider).filter(
        AuthProvider.provider == AuthProvider.GOOGLE
    ).count() == 0


# ---------------------------------------------------------------------------
# Profile extraction
# ---------------------------------------------------------------------------

def test_google_profile_carries_through_email_verified_claim():
    profile = profile_from_google({}, {"sub": "1", "email": "a@b.com", "email_verified": False})
    assert profile.email_verified is False


def test_google_profile_requires_an_email():
    with pytest.raises(OAuthError):
        profile_from_google({}, {"sub": "1"})


def test_github_profile_prefers_the_primary_verified_email():
    profile = profile_from_github(
        {"id": 7, "name": "G"},
        [
            {"email": "secondary@x.com", "primary": False, "verified": True},
            {"email": "primary@x.com", "primary": True, "verified": True},
        ],
    )
    assert profile.email == "primary@x.com"


def test_github_profile_never_picks_an_unverified_email():
    """GitHub's public email can be unverified; it must not be trusted."""
    profile = profile_from_github(
        {"id": 7, "name": "G"},
        [
            {"email": "unverified@x.com", "primary": True, "verified": False},
            {"email": "verified@x.com", "primary": False, "verified": True},
        ],
    )
    assert profile.email == "verified@x.com"


def test_github_profile_with_no_verified_email_is_an_error():
    with pytest.raises(OAuthError):
        profile_from_github(
            {"id": 7}, [{"email": "u@x.com", "primary": True, "verified": False}]
        )


def test_github_profile_lowercases_email():
    profile = profile_from_github(
        {"id": 7}, [{"email": "MiXeD@X.com", "primary": True, "verified": True}]
    )
    assert profile.email == "mixed@x.com"


# ---------------------------------------------------------------------------
# Provider discovery endpoint
# ---------------------------------------------------------------------------

def test_providers_endpoint_lists_configured_providers(client):
    resp = client.get("/api/auth/oauth/providers")
    assert resp.status_code == 200
    # conftest sets placeholder credentials for both.
    assert sorted(resp.json()["providers"]) == ["github", "google"]


def test_unknown_provider_is_404(client):
    assert client.get("/api/auth/oauth/apple/login").status_code == 404
