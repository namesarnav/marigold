from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User

bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()

ALGORITHM = "HS256"

# Returned in the `detail` of every 403 raised by `get_verified_user`. The
# frontend switches on this string to render the "check your email"
# interstitial, so it is part of the API contract — do not reword it casually.
EMAIL_VERIFICATION_REQUIRED = "email_verification_required"


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller. Says nothing about whether their email is verified.

    Use this only for endpoints an unverified user must still reach — `/me`,
    and the resend-verification flow. Everything else wants `get_verified_user`.
    """
    # The Authorization header is checked FIRST, and the session cookie is only
    # a fallback. The order matters and used to be the other way around, which
    # was a real multi-user bug: a browser (or a test client) holding a session
    # cookie for user A would be resolved as A even when it presented a valid
    # bearer token for user B. An explicitly supplied credential must always win
    # over ambient one, otherwise a stale cookie silently overrides the caller's
    # actual identity.
    if credentials is not None:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
            uid_str = payload.get("sub")
            if uid_str is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
                )
            user_id = int(uid_str)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )
        return user

    # No bearer token: fall back to the OAuth session cookie.
    user_id_str = request.session.get("user_id")
    if user_id_str:
        user = db.query(User).filter(User.id == int(user_id_str)).first()
        if user:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


def get_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """The gate for every core feature: authenticated *and* email-verified.

    This is the single choke point for the Phase 3 hard block, which is why it
    is a dependency rather than a check repeated per route — a new endpoint that
    depends on this is covered automatically, including any future Stripe
    checkout route. (There is no Stripe integration in the codebase today; when
    one is added it must depend on this, not on `get_current_user`.)

    403 rather than 401: the credentials are valid, the account just is not
    permitted yet. A 401 would make the frontend's refresh-and-retry logic spin.
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": EMAIL_VERIFICATION_REQUIRED,
                "message": (
                    "Confirm your email address to use Marigold. Check your "
                    "inbox for the verification link."
                ),
                "email": current_user.email,
            },
        )
    return current_user
