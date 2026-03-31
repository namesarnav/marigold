"""Password handling and single-use signed email tokens.

Two things live here that the auth routes must not re-implement inline:

1. Password strength, enforced server-side. The frontend has its own checks,
   but they are advisory — an attacker posts straight to the API, so this is
   the only rule that counts.
2. Verification / reset tokens. These are itsdangerous-signed (tamper-proof,
   self-expiring) *and* recorded in `email_tokens` so they can be spent exactly
   once. A signature alone cannot be revoked; see `EmailToken`.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .models import EmailToken, User

settings = get_settings()

# bcrypt silently truncates at 72 *bytes*. Rejecting longer input is better than
# quietly ignoring the tail, which would make two different passwords equivalent.
BCRYPT_MAX_BYTES = 72

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# Passwords that pass a naive "length + complexity" rule but are still the first
# things any credential-stuffing list tries.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd", "p@ssw0rd", "p@ssword",
    "qwerty", "qwerty123", "qwertyuiop", "letmein", "welcome", "welcome1",
    "iloveyou", "admin", "administrator", "root", "changeme", "secret",
    "monkey", "dragon", "sunshine", "princess", "football", "baseball",
    "abc123", "123456", "1234567", "12345678", "123456789", "1234567890",
    "111111", "000000", "trustno1", "master", "superman", "batman",
    "flashlearn", "marigold",
}


class PasswordPolicyError(ValueError):
    """Raised when a candidate password fails the server-side strength rule."""


def _normalize(password: str) -> str:
    # NFKC so that visually identical passwords hash identically across
    # platforms/keyboards; a user typing the same thing must always get in.
    return unicodedata.normalize("NFKC", password)


def validate_password_strength(password: str, *, email: str = "", name: str = "") -> None:
    """Raise PasswordPolicyError unless `password` meets the policy.

    Rule: 12-128 chars, at least three of the four character classes, not a
    known-common password, and not simply the user's own email or name.
    """
    if not isinstance(password, str) or not password:
        raise PasswordPolicyError("Password is required.")

    pw = _normalize(password)

    if len(pw) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(pw) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if len(pw.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise PasswordPolicyError(
            "Password is too long to be hashed securely; please use a shorter one."
        )

    classes = sum(
        bool(re.search(pattern, pw))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    if classes < 3:
        raise PasswordPolicyError(
            "Password must include at least three of: lowercase, uppercase, "
            "digits, symbols."
        )

    folded = pw.casefold()
    if folded in _COMMON_PASSWORDS:
        raise PasswordPolicyError("That password is too common. Please choose another.")

    # Strip digits/symbols before the common-word check so "Password123!" is
    # still caught by the same list.
    stripped = re.sub(r"[^a-z]", "", folded)
    if stripped and stripped in _COMMON_PASSWORDS:
        raise PasswordPolicyError("That password is too common. Please choose another.")

    if re.fullmatch(r"(.)\1*", pw):
        raise PasswordPolicyError("Password must not be a single repeated character.")

    local_part = email.split("@")[0].casefold() if email else ""
    for personal in (email.casefold(), local_part, name.casefold() if name else ""):
        if personal and len(personal) >= 4 and personal in folded:
            raise PasswordPolicyError(
                "Password must not contain your name or email address."
            )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_normalize(password).encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    """Password check that tolerates a missing hash without leaking that fact.

    OAuth-only accounts have `password_hash = None`. Returning False immediately
    would let an attacker distinguish "OAuth-only account" from "no such
    account" by response timing, so we still run one bcrypt comparison against a
    dummy hash before failing.
    """
    if not hashed:
        bcrypt.checkpw(b"dummy-password", _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(_normalize(plain).encode("utf-8"), hashed.encode())
    except (ValueError, TypeError):
        return False


# Computed once at import: the cost of a real bcrypt round, for the timing
# equalisation above.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt())


# --- Signed, single-use email tokens ---------------------------------------

_SALTS = {
    EmailToken.VERIFY: "marigold.email-verification.v1",
    EmailToken.RESET: "marigold.password-reset.v1",
}


def _serializer(purpose: str) -> URLSafeTimedSerializer:
    try:
        salt = _SALTS[purpose]
    except KeyError:  # pragma: no cover - guarded by callers
        raise ValueError(f"Unknown token purpose: {purpose!r}")
    # The salt is what stops a verification token being replayed as a reset
    # token: same key, different namespace, so signatures do not cross over.
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_max_age_seconds(purpose: str) -> int:
    if purpose == EmailToken.RESET:
        return settings.reset_token_expire_minutes * 60
    return settings.verification_token_expire_minutes * 60


def issue_email_token(db: Session, user: User, purpose: str) -> str:
    """Mint a signed token for `user` and record it as spendable exactly once.

    Any outstanding unused token of the same purpose is invalidated first, so a
    freshly requested link is always the only working one.
    """
    invalidate_outstanding_tokens(db, user.id, purpose)

    payload = {"uid": user.id, "purpose": purpose, "nonce": secrets.token_urlsafe(8)}
    token = _serializer(purpose).dumps(payload)

    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_token_hash(token),
            expires_at=datetime.utcnow()
            + timedelta(seconds=token_max_age_seconds(purpose)),
        )
    )
    db.commit()
    return token


def invalidate_outstanding_tokens(db: Session, user_id: int, purpose: str) -> None:
    now = datetime.utcnow()
    (
        db.query(EmailToken)
        .filter(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .update({EmailToken.used_at: now}, synchronize_session=False)
    )
    db.commit()


class TokenError(Exception):
    """Token was missing, forged, expired, or already spent."""


def consume_email_token(db: Session, token: str, purpose: str) -> User:
    """Validate `token` and spend it, returning the user it belongs to.

    Every failure mode raises `TokenError`. Expiry is checked twice on purpose:
    once by the signer (`max_age`) and once against the stored `expires_at`, so
    shortening the configured lifetime takes effect on already-issued tokens.
    """
    if not token:
        raise TokenError("Missing token.")

    try:
        payload = _serializer(purpose).loads(
            token, max_age=token_max_age_seconds(purpose)
        )
    except SignatureExpired:
        raise TokenError("This link has expired. Please request a new one.")
    except BadSignature:
        raise TokenError("This link is invalid. Please request a new one.")

    if not isinstance(payload, dict) or payload.get("purpose") != purpose:
        raise TokenError("This link is invalid. Please request a new one.")

    record = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == _token_hash(token))
        .first()
    )
    if record is None:
        raise TokenError("This link is invalid. Please request a new one.")
    if record.used_at is not None:
        raise TokenError("This link has already been used. Please request a new one.")
    if record.expires_at < datetime.utcnow():
        raise TokenError("This link has expired. Please request a new one.")
    if record.purpose != purpose or record.user_id != payload.get("uid"):
        raise TokenError("This link is invalid. Please request a new one.")

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise TokenError("This link is invalid. Please request a new one.")

    record.used_at = datetime.utcnow()
    db.commit()
    return user
