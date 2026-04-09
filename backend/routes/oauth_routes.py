"""OAuth sign-in endpoints for Google and GitHub.

The browser leaves and comes back, so the callback cannot return JSON — it
redirects into the SPA. Notably it does **not** put an access token in the
redirect URL: URLs leak through history, `Referer`, and server logs. Instead the
callback sets the same httpOnly refresh cookie the password flow uses and sends
the browser to `/oauth/callback`, where the SPA calls `/api/auth/refresh` to
pick up an access token. That keeps JWT as the session mechanism with no new
token-transport surface.

Authlib owns the state parameter, the code exchange, and PKCE for Google.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..oauth import (
    AccountConflictError,
    OAuthError,
    configured_providers,
    get_client,
    profile_from_github,
    profile_from_google,
    provider_configured,
    resolve_oauth_login,
)
from ..models import AuthProvider
from ..schemas import OAuthProvidersResponse
from .auth import establish_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/oauth", tags=["auth"])
settings = get_settings()

SUPPORTED = (AuthProvider.GOOGLE, AuthProvider.GITHUB)


def _frontend(path: str, **params) -> str:
    base = settings.frontend_base_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}{path}{query}"


def _fail(code: str, message: str) -> RedirectResponse:
    """Bounce back to the login screen with something the UI can render."""
    return RedirectResponse(
        _frontend("/login", error=code, message=message),
        status_code=status.HTTP_302_FOUND,
    )


def _callback_url(request: Request, provider: str) -> str:
    """The redirect URI registered with the provider.

    Built from `backend_base_url` rather than from the incoming request, because
    it has to match the value registered in the provider console byte for byte,
    and behind an ingress the request's own host/scheme may not.
    """
    base = settings.backend_base_url.rstrip("/")
    return f"{base}/api/auth/oauth/{provider}/callback"


@router.get("/providers", response_model=OAuthProvidersResponse)
def list_providers():
    """Which providers actually have credentials, so the UI only shows those."""
    return OAuthProvidersResponse(providers=configured_providers())


@router.get("/{provider}/login")
async def oauth_login(provider: str, request: Request):
    if provider not in SUPPORTED:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if not provider_configured(provider):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider} sign-in is not configured on this server.",
        )
    client = get_client(provider)
    # authorize_redirect stores state (and the PKCE verifier) in the session
    # cookie; the callback below is what consumes and validates them.
    return await client.authorize_redirect(request, _callback_url(request, provider))


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str, request: Request, db: Session = Depends(get_db)
):
    if provider not in SUPPORTED:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if not provider_configured(provider):
        return _fail(
            "provider_not_configured",
            f"{provider} sign-in is not configured on this server.",
        )

    # The provider can also report failure by redirecting here with ?error=.
    if request.query_params.get("error"):
        return _fail(
            "provider_denied",
            request.query_params.get("error_description")
            or "Sign-in was cancelled or denied.",
        )

    client = get_client(provider)

    try:
        # Validates `state` and, for Google, the PKCE verifier.
        token = await client.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001 - Authlib raises several types
        logger.warning("%s token exchange failed: %s", provider, exc)
        return _fail("exchange_failed", "Sign-in failed. Please try again.")

    try:
        if provider == AuthProvider.GOOGLE:
            userinfo = token.get("userinfo")
            if not userinfo:
                userinfo = await client.userinfo(token=token)
            profile = profile_from_google(token, dict(userinfo))
        else:
            resp = await client.get("user", token=token)
            resp.raise_for_status()
            emails_resp = await client.get("user/emails", token=token)
            emails_resp.raise_for_status()
            profile = profile_from_github(resp.json(), emails_resp.json())
    except OAuthError as exc:
        return _fail("profile_unavailable", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s profile fetch failed: %s", provider, exc)
        return _fail("profile_unavailable", "Could not read your profile. Try again.")

    try:
        user, created = resolve_oauth_login(db, profile)
    except AccountConflictError as exc:
        # Phase 4, case 2. Surfaced explicitly rather than silently linking.
        return RedirectResponse(
            _frontend(
                "/login",
                error="unverified_account_exists",
                message=exc.message,
                email=exc.email,
            ),
            status_code=status.HTTP_302_FOUND,
        )
    except OAuthError as exc:
        return _fail("oauth_failed", str(exc))
    except IntegrityError:
        db.rollback()
        # Two callbacks racing for the same new account; the unique constraints
        # in auth_providers did their job.
        return _fail("oauth_failed", "Sign-in failed. Please try again.")

    redirect = RedirectResponse(
        _frontend("/oauth/callback", provider=provider, new="1" if created else "0"),
        status_code=status.HTTP_302_FOUND,
    )
    # Sets the httpOnly refresh cookie on the redirect response; the SPA trades
    # it for an access token via /api/auth/refresh.
    establish_session(request, redirect, db, user)
    return redirect
