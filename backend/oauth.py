"""OAuth provider registry (Authlib) and the account-linking decision.

The linking decision is deliberately a pure function over the database —
`resolve_oauth_login` — rather than something woven into the callback handler.
It is the place an account-takeover bug would live, so it is kept small enough
to read in one sitting and testable without standing up an HTTP flow.

Token exchange, `state`, and PKCE are all Authlib's job; nothing here
hand-rolls them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuthProvider, User

logger = logging.getLogger(__name__)
settings = get_settings()

GOOGLE = AuthProvider.GOOGLE
GITHUB = AuthProvider.GITHUB


@dataclass(frozen=True)
class ProviderProfile:
    """The bits of a provider's user profile that we actually act on."""

    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    name: Optional[str] = None


class OAuthError(Exception):
    """The provider flow failed or returned something unusable."""


class AccountConflictError(Exception):
    """OAuth email belongs to an existing account that is not yet verified.

    Linking here would let anyone who can obtain a provider account for an
    address take over a local account registered with that same address before
    its owner ever proved they control it. We refuse and surface the conflict.
    """

    def __init__(self, email: str, message: str) -> None:
        super().__init__(message)
        self.email = email
        self.message = message


# --- Registry ---------------------------------------------------------------

oauth = OAuth()

_GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def _register_clients() -> None:
    """Register whichever providers have credentials configured.

    Registering with placeholder credentials is fine and intended for the
    checkpoint: the flow builds and the redirect is constructed correctly, and
    only the provider's own response will reject it.
    """
    if settings.google_client_id and settings.google_client_secret:
        oauth.register(
            name=GOOGLE,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url=_GOOGLE_METADATA,
            client_kwargs={
                "scope": "openid email profile",
                # Authlib generates and verifies the PKCE pair itself.
                "code_challenge_method": "S256",
            },
        )
    if settings.github_client_id and settings.github_client_secret:
        oauth.register(
            name=GITHUB,
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )


_register_clients()


def provider_configured(provider: str) -> bool:
    if provider == GOOGLE:
        return bool(settings.google_client_id and settings.google_client_secret)
    if provider == GITHUB:
        return bool(settings.github_client_id and settings.github_client_secret)
    return False


def configured_providers() -> list[str]:
    return [p for p in (GOOGLE, GITHUB) if provider_configured(p)]


def get_client(provider: str):
    client = oauth.create_client(provider)
    if client is None:
        raise OAuthError(f"{provider} sign-in is not configured on this server.")
    return client


# --- Profile extraction -----------------------------------------------------


def profile_from_google(token: dict, userinfo: dict) -> ProviderProfile:
    """Build a profile from Google's OIDC id_token claims.

    `email_verified` is carried through rather than assumed: Google can issue
    claims for addresses it has not verified (some Workspace configurations),
    and we only trust an address the provider itself vouches for.
    """
    sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    if not sub or not email:
        raise OAuthError("Google did not return an email address for this account.")
    return ProviderProfile(
        provider=GOOGLE,
        provider_user_id=str(sub),
        email=email,
        email_verified=bool(userinfo.get("email_verified")),
        name=userinfo.get("name") or None,
    )


def profile_from_github(user_data: dict, emails: list[dict]) -> ProviderProfile:
    """Build a profile from GitHub's REST responses.

    GitHub's `/user` endpoint returns whatever the user set as their public
    email, which may be unverified or absent, so the address comes from
    `/user/emails` and must be both primary and verified.
    """
    uid = user_data.get("id")
    if not uid:
        raise OAuthError("GitHub did not return a user id.")

    chosen = None
    for entry in emails or []:
        if entry.get("primary") and entry.get("verified"):
            chosen = entry.get("email")
            break
    if not chosen:
        # Fall back to any verified address; still never an unverified one.
        for entry in emails or []:
            if entry.get("verified"):
                chosen = entry.get("email")
                break
    if not chosen:
        raise OAuthError(
            "Your GitHub account has no verified email address. Verify one on "
            "GitHub and try again."
        )

    return ProviderProfile(
        provider=GITHUB,
        provider_user_id=str(uid),
        email=chosen.strip().lower(),
        email_verified=True,
        name=user_data.get("name") or user_data.get("login") or None,
    )


# --- The linking decision ---------------------------------------------------


def resolve_oauth_login(db: Session, profile: ProviderProfile) -> tuple[User, bool]:
    """Find, link, or create the account behind an OAuth profile.

    Returns `(user, created)`. Raises `AccountConflictError` for the unverified
    collision case. The three cases from the spec, plus the returning-user case
    that has to come first:

    0. This provider identity is already linked -> that account, no email lookup.
       Checked first so that a user who later changed their email at the
       provider is not treated as a stranger.
    1. Email matches a VERIFIED account -> link this provider to it.
    2. Email matches an UNVERIFIED account -> refuse, raise AccountConflictError.
    3. No match -> create the account, already verified, and link.
    """
    if not profile.email_verified:
        # Case 2's threat in a different wrapper: an unverified provider address
        # is not evidence of anything, so it must never match an account.
        raise OAuthError(
            f"Your {profile.provider} email address is not verified. Verify it "
            f"with {profile.provider} and try again."
        )

    email = profile.email.strip().lower()

    # Case 0 — returning user, identified by provider subject id.
    link = (
        db.query(AuthProvider)
        .filter(
            AuthProvider.provider == profile.provider,
            AuthProvider.provider_user_id == profile.provider_user_id,
        )
        .first()
    )
    if link is not None:
        user = db.query(User).filter(User.id == link.user_id).first()
        if user is None:  # pragma: no cover - FK makes this unreachable
            raise OAuthError("Linked account no longer exists.")
        if not user.email_verified:
            # The account was created through OAuth, so it was verified at
            # creation. Reaching here means something else cleared the flag;
            # trust the provider and restore it rather than locking the user out.
            user.email_verified = True
            db.commit()
        return user, False

    existing = db.query(User).filter(User.email == email).first()

    # Case 3 — no account with this address yet.
    if existing is None:
        user = User(
            email=email,
            password_hash=None,
            email_verified=True,  # the provider verified it; see spec Phase 4
            name=profile.name,
        )
        db.add(user)
        db.flush()
        db.add(
            AuthProvider(
                user_id=user.id,
                provider=profile.provider,
                provider_user_id=profile.provider_user_id,
            )
        )
        db.commit()
        db.refresh(user)
        return user, True

    # Case 2 — an unverified local account already owns this address.
    if not existing.email_verified:
        logger.warning(
            "Blocked %s OAuth link to unverified account %s", profile.provider, email
        )
        raise AccountConflictError(
            email=email,
            message=(
                "An account with this email already exists but has not been "
                "verified yet. Check your inbox and confirm that address first, "
                f"then sign in with {profile.provider}."
            ),
        )

    # Case 1 — verified account: link this provider onto it.
    if not existing.name and profile.name:
        existing.name = profile.name
    db.add(
        AuthProvider(
            user_id=existing.id,
            provider=profile.provider,
            provider_user_id=profile.provider_user_id,
        )
    )
    db.commit()
    db.refresh(existing)
    return existing, False
