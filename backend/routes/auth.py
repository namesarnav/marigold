from datetime import datetime, timedelta
from hashlib import sha256
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie, status
from jose import jwt
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import ALGORITHM, get_current_user
from ..models import RefreshToken, User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

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

@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email,
        password_hash=_hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = str(user.id)
    request.session["user_name"] = user.name

    access_token = _create_access_token(user.id)
    refresh_raw = _create_refresh_token(user.id, db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        max_age=settings.refresh_token_expire_days * 86400,
        samesite="lax",
    )
    return TokenResponse(access_token=access_token)

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    request.session["user_id"] = str(user.id)
    request.session["user_name"] = user.name

    access_token = _create_access_token(user.id)
    refresh_raw = _create_refresh_token(user.id, db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        max_age=settings.refresh_token_expire_days * 86400,
        samesite="lax",
    )
    return TokenResponse(access_token=access_token)

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

    access_token = _create_access_token(db_token.user_id)
    refresh_raw = _create_refresh_token(db_token.user_id, db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        max_age=settings.refresh_token_expire_days * 86400,
        samesite="lax",
    )
    return TokenResponse(access_token=access_token)

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
def me(current_user: User = Depends(get_current_user)):
    return current_user
