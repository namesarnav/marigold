from datetime import datetime, timedelta
from hashlib import sha256

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jose import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import ALGORITHM, get_current_user
from ..mailer import send_password_reset_email, send_verification_email
from ..models import AuthProvider, EmailToken, RefreshToken, User
from ..ratelimit import (
    client_ip,
    get_limiter,
    login_account_key,
    login_ip_key,
    password_reset_key,
    resend_verification_key,
)
from ..schemas import (
    EmailOnlyRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from ..security import (
    PasswordPolicyError,
    TokenError,
    consume_email_token,
    hash_password,
    issue_email_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

# One message for every login failure. Whether the address is unknown, the
# password is wrong, or the account is OAuth-only must not be distinguishable.
GENERIC_LOGIN_ERROR = "Invalid email or password."

# Likewise for the two "we emailed you if you exist" endpoints.
GENERIC_EMAIL_SENT = (
    "If an account exists for that address, we've sent an email. "
    "Check your inbox."
)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _auth_methods(db: Session, user: User) -> list[str]:
    rows = (
        db.query(AuthProvider.provider)
        .filter(AuthProvider.user_id == user.id)
        .order_by(AuthProvider.created_at)
        .all()
    )
    methods = [r[0] for r in rows]
    # Defensive: an account created before auth_providers existed still has a
    # usable password, so report it even without a backing row.
    if user.password_hash and AuthProvider.PASSWORD not in methods:
        methods.insert(0, AuthProvider.PASSWORD)
    return methods


def user_out(db: Session, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified=bool(user.email_verified),
        auth_methods=_auth_methods(db, user),
    )


def _create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def _create_refresh_token(user_id: int, db: Session) -> str:
    import secrets

    raw = secrets.token_hex(32)
    token_hash = sha256(raw.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(db_token)
    db.commit()
    return raw


def _revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    """Log every existing session out. Used after a password reset."""
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
        .update({RefreshToken.revoked: True}, synchronize_session=False)
    )
    db.commit()


def establish_session(
    request: Request, response: Response, db: Session, user: User
) -> TokenResponse:
    """Issue the JWT + rotating refresh cookie and populate the server session.

    JWT stays the session mechanism, unchanged from before this upgrade.
    """
    request.session["user_id"] = str(user.id)
    request.session["user_name"] = user.name or ""

    access_token = _create_access_token(user.id)
    refresh_raw = _create_refresh_token(user.id, db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        max_age=settings.refresh_token_expire_days * 86400,
        samesite="lax",
    )
    return TokenResponse(
        access_token=access_token,
        email_verified=bool(user.email_verified),
        user=user_out(db, user),
    )


def _send_verification(db: Session, user: User) -> None:
    token = issue_email_token(db, user, EmailToken.VERIFY)
    send_verification_email(user.email, user.name, token)


# --- Registration & login ---------------------------------------------------


@router.post("/register", response_model=TokenResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = _normalize_email(payload.email)

    try:
        from ..security import validate_password_strength

        validate_password_strength(payload.password, email=email, name=payload.name)
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        email_verified=False,  # Phase 3: nothing works until the link is clicked.
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            AuthProvider(
                user_id=user.id,
                provider=AuthProvider.PASSWORD,
                provider_user_id=None,
            )
        )
        db.commit()
    except IntegrityError:
        # Two concurrent signups for the same address; the unique index wins.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    db.refresh(user)

    _send_verification(db, user)
    return establish_session(request, response, db, user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate, throttled per account and per IP.

    Only *failed* attempts are counted, and a success clears the account's
    counter, so ordinary users never throttle themselves. Note the residual
    trade-off: because the account budget is keyed on email, an attacker can
    still deliberately burn a known victim's budget to lock them out for the
    window. That is inherent to per-account throttling; the per-IP limit is what
    keeps it expensive, and the window is deliberately short.
    """
    email = _normalize_email(payload.email)
    limiter = get_limiter()
    account_key = login_account_key(email)
    ip_key = login_ip_key(client_ip(request))
    window = settings.login_attempt_window_seconds

    if limiter.peek_blocked(account_key, limit=settings.login_max_attempts_per_account):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(window)},
        )
    if limiter.peek_blocked(ip_key, limit=settings.login_max_attempts_per_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(window)},
        )

    user = db.query(User).filter(User.email == email).first()
    # verify_password burns a bcrypt round even when `user` is None, so the
    # unknown-account and wrong-password paths cost the same wall time.
    if user is None or not verify_password(payload.password, user.password_hash):
        limiter.hit(
            account_key,
            limit=settings.login_max_attempts_per_account,
            window_seconds=window,
        )
        limiter.hit(
            ip_key, limit=settings.login_max_attempts_per_ip, window_seconds=window
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR
        )

    limiter.reset(account_key)
    return establish_session(request, response, db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, refresh_token: str = Cookie(default=None), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    token_hash = sha256(refresh_token.encode()).hexdigest()
    db_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,  # noqa: E712
    ).first()

    if not db_token or db_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    db_token.revoked = True
    db.commit()

    user = db.query(User).filter(User.id == db_token.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = _create_access_token(user.id)
    refresh_raw = _create_refresh_token(user.id, db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        max_age=settings.refresh_token_expire_days * 86400,
        samesite="lax",
    )
    return TokenResponse(
        access_token=access_token,
        email_verified=bool(user.email_verified),
        user=user_out(db, user),
    )


@router.post("/logout")
def logout(request: Request, response: Response, refresh_token: str = Cookie(default=None), db: Session = Depends(get_db)):
    if refresh_token:
        token_hash = sha256(refresh_token.encode()).hexdigest()
        db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if db_token:
            db_token.revoked = True
            db.commit()
    request.session.clear()
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deliberately *not* behind `get_verified_user`.

    An unverified account has to be able to read its own state — that is what
    drives the "check your email" interstitial.
    """
    return user_out(db, current_user)


# --- Email verification -----------------------------------------------------


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Spend a verification token and mark the account verified.

    Returns a fresh session so clicking the link in a new browser logs the user
    straight in, rather than bouncing them to a login form.
    """
    try:
        user = consume_email_token(db, payload.token, EmailToken.VERIFY)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not user.email_verified:
        user.email_verified = True
        db.commit()
        db.refresh(user)

    return establish_session(request, response, db, user)


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: EmailOnlyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Re-send the verification link, rate limited per address.

    Answers identically for unknown addresses and already-verified accounts so
    it cannot be used to enumerate accounts or to check verification status.
    """
    email = _normalize_email(payload.email)
    limiter = get_limiter()
    status_ = limiter.hit(
        resend_verification_key(email),
        limit=settings.resend_verification_max_per_hour,
        window_seconds=3600,
    )
    if not status_.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification emails requested. Please try again later.",
            headers={"Retry-After": str(status_.retry_after_seconds)},
        )

    user = db.query(User).filter(User.email == email).first()
    # Only actually send for an unverified, password-capable account. Every
    # other case falls through to the same response.
    if user is not None and not user.email_verified:
        _send_verification(db, user)

    return MessageResponse(message=GENERIC_EMAIL_SENT)


# --- Password reset ---------------------------------------------------------


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: EmailOnlyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = _normalize_email(payload.email)
    limiter = get_limiter()
    status_ = limiter.hit(
        password_reset_key(email),
        limit=settings.password_reset_max_per_hour,
        window_seconds=3600,
    )
    if not status_.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password reset requests. Please try again later.",
            headers={"Retry-After": str(status_.retry_after_seconds)},
        )

    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        token = issue_email_token(db, user, EmailToken.RESET)
        send_password_reset_email(user.email, user.name, token)

    return MessageResponse(message=GENERIC_EMAIL_SENT)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password from a reset link.

    The token is validated and spent before the password is touched, and every
    existing refresh token is revoked afterwards so a session an attacker may
    already hold does not survive the reset.
    """
    try:
        user = consume_email_token(db, payload.token, EmailToken.RESET)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        from ..security import validate_password_strength

        validate_password_strength(payload.password, email=user.email, name=user.name or "")
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    user.password_hash = hash_password(payload.password)

    # Completing a reset proves control of the mailbox, so it doubles as email
    # verification for an account that never confirmed.
    if not user.email_verified:
        user.email_verified = True

    # An OAuth-only account that sets a password gains a new sign-in method.
    has_password_row = (
        db.query(AuthProvider)
        .filter(
            AuthProvider.user_id == user.id,
            AuthProvider.provider == AuthProvider.PASSWORD,
        )
        .first()
    )
    if has_password_row is None:
        db.add(
            AuthProvider(
                user_id=user.id, provider=AuthProvider.PASSWORD, provider_user_id=None
            )
        )

    db.commit()

    _revoke_all_refresh_tokens(db, user.id)
    return MessageResponse(message="Your password has been reset. You can now sign in.")
