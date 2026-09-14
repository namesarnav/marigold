"""The settings derivation that only ever runs in a deployed container.

Everything here fails *silently* in production if it regresses — the app boots,
the health check passes, and the damage shows up as a sign-in that redirects to
localhost or a session cookie sent in cleartext. None of it is reachable from
the rest of the suite, which runs with explicit localhost values, so it needs
its own coverage.

`Settings()` is constructed directly rather than through `get_settings()`: that
is `lru_cache`d and already populated by conftest, and clearing it mid-suite
would hand a different config to modules that captured the old one at import.
"""

import pytest
from conftest import register_user

from backend.config import Settings

# Enough to satisfy the two fields with no default. The values are irrelevant
# to what is under test here.
REQUIRED = {"gemini_api_key": "fake", "secret_key": "test"}

RAILWAY_DOMAIN = "marigold-production.up.railway.app"
RAILWAY_ORIGIN = f"https://{RAILWAY_DOMAIN}"


@pytest.fixture
def on_railway(monkeypatch):
    """Simulate a Railway deployment by injecting the domain it provides."""
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", RAILWAY_DOMAIN)


# conftest exports these for the rest of the suite, and an exported value counts
# as explicitly supplied — which is precisely what suppresses the derivation
# under test. Clearing them here is what lets these tests see a container's
# environment rather than the suite's.
DERIVED_FIELDS = (
    "RAILWAY_PUBLIC_DOMAIN",
    "PUBLIC_URL",
    "FRONTEND_BASE_URL",
    "BACKEND_BASE_URL",
    "CORS_ORIGINS",
    "COOKIE_SECURE",
    "COOKIE_SAMESITE",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in DERIVED_FIELDS:
        monkeypatch.delenv(name, raising=False)


# --- Public URLs ------------------------------------------------------------


def test_public_urls_come_from_the_railway_domain(on_railway):
    """Emailed links and OAuth callbacks must point at the deployed host.

    Left at their defaults these send a real user to http://localhost:5173,
    which works perfectly on the developer's machine and nowhere else.
    """
    settings = Settings(**REQUIRED)

    assert settings.frontend_base_url == RAILWAY_ORIGIN
    assert settings.backend_base_url == RAILWAY_ORIGIN
    assert settings.cors_origin_list == [RAILWAY_ORIGIN]


def test_cookie_is_marked_secure_when_deployed(on_railway):
    """Railway serves over HTTPS, so the session cookie must carry Secure."""
    assert Settings(**REQUIRED).cookie_secure is True


def test_an_explicit_value_beats_the_derived_one(on_railway):
    """A custom domain is configured the ordinary way and is not overwritten."""
    custom = "https://marigold.example.com"

    settings = Settings(**REQUIRED, frontend_base_url=custom)

    assert settings.frontend_base_url == custom
    # Only the field that was supplied is pinned; the rest still derive.
    assert settings.backend_base_url == RAILWAY_ORIGIN


def test_localhost_defaults_survive_off_railway():
    """No Railway domain means local development, which is plain HTTP."""
    settings = Settings(**REQUIRED)

    assert settings.frontend_base_url == "http://localhost:5173"
    assert settings.backend_base_url == "http://localhost:8000"
    assert settings.cookie_secure is False


# --- PUBLIC_URL -------------------------------------------------------------
#
# The two-service deployment: the browser talks to the frontend service, whose
# nginx proxies /api to this one. The API's own RAILWAY_PUBLIC_DOMAIN is then the
# WRONG public address, and PUBLIC_URL has to override it.

WEB_ORIGIN = "https://marigold-web-production.up.railway.app"


def test_public_url_beats_the_services_own_railway_domain(on_railway):
    """OAuth callbacks and emailed links must go to the proxy, not the API host.

    The API host serves only JSON, so a sign-in bounced there dead-ends, and a
    refresh cookie set there is invisible to the frontend's origin.
    """
    settings = Settings(**REQUIRED, public_url=WEB_ORIGIN)

    assert settings.frontend_base_url == WEB_ORIGIN
    assert settings.backend_base_url == WEB_ORIGIN
    assert settings.cors_origin_list == [WEB_ORIGIN]
    assert settings.cookie_secure is True


def test_public_url_drops_a_trailing_slash():
    """Otherwise every derived link gains a double slash."""
    settings = Settings(**REQUIRED, public_url=WEB_ORIGIN + "/")

    assert settings.frontend_base_url == WEB_ORIGIN
    assert settings.public_url == WEB_ORIGIN


def test_public_url_over_plain_http_does_not_mark_the_cookie_secure():
    """A Secure cookie is never sent over http, which would break a local proxy."""
    settings = Settings(**REQUIRED, public_url="http://localhost:8081")

    assert settings.cookie_secure is False


def test_public_url_without_a_scheme_is_refused():
    """"marigold.up.railway.app" alone would produce links with no scheme."""
    with pytest.raises(ValueError, match="PUBLIC_URL"):
        Settings(**REQUIRED, public_url="marigold-web-production.up.railway.app")


def test_explicit_urls_still_beat_public_url():
    custom = "https://api.example.com"

    settings = Settings(**REQUIRED, public_url=WEB_ORIGIN, backend_base_url=custom)

    assert settings.backend_base_url == custom
    assert settings.frontend_base_url == WEB_ORIGIN


# --- Cookie SameSite ----------------------------------------------------------


def test_samesite_none_boots_when_secure_is_left_to_derivation(on_railway):
    """Regression: this configuration used to refuse to start.

    The SameSite check ran before _apply_railway_defaults had derived
    cookie_secure, so it saw the default False and raised. Pydantic runs
    after-validators in definition order; the check now runs last.
    """
    settings = Settings(**REQUIRED, cookie_samesite="none")

    assert settings.cookie_samesite == "none"
    assert settings.cookie_secure is True


def test_samesite_none_without_secure_is_still_refused():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(**REQUIRED, cookie_samesite="none", cookie_secure=False)


# --- Database URL -----------------------------------------------------------


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_a_driverless_postgres_url_is_pinned_to_psycopg(scheme):
    """Railway's DATABASE_URL has no driver, and the default one is not installed.

    SQLAlchemy resolves a bare `postgresql://` to psycopg2; requirements.txt
    ships psycopg 3. Without this rewrite, referencing the database the way
    Railway documents crashes the container at import.
    """
    settings = Settings(**REQUIRED, database_url=f"{scheme}://u:p@host:5432/marigold")

    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/marigold"


def test_rewriting_preserves_the_rest_of_the_url():
    """Only the scheme changes — credentials, port, path and query survive."""
    settings = Settings(
        **REQUIRED,
        database_url="postgresql://u:p%40ss@host:5432/db?sslmode=require",
    )

    assert settings.database_url == (
        "postgresql+psycopg://u:p%40ss@host:5432/db?sslmode=require"
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@host/db",
        "postgresql+asyncpg://u:p@host/db",
        "sqlite:///./flashlearn.db",
        "sqlite:///:memory:",
    ],
)
def test_an_explicit_driver_is_left_alone(url):
    """Choosing a driver is the operator's call; only the bare scheme is fixed."""
    assert Settings(**REQUIRED, database_url=url).database_url == url


# --- Cookie flags -----------------------------------------------------------


def test_refresh_cookie_follows_the_secure_setting(monkeypatch, client):
    """The refresh token must not be sent over cleartext once deployed.

    It is the longest-lived credential the app issues and on its own is enough
    to mint access tokens, yet it was the one cookie set without `secure` —
    `settings.cookie_secure` drove only the session cookie. Asserted through a
    real login rather than by reading the setting, because the gap was in the
    call site, not the config.
    """
    from backend.routes import auth as auth_routes

    monkeypatch.setattr(auth_routes.settings, "cookie_secure", True, raising=False)

    response = register_user(client, email="cookie-flags@example.com")

    refresh = response.headers["set-cookie"]
    assert "refresh_token=" in refresh
    assert "Secure" in refresh
    assert "HttpOnly" in refresh


def test_refresh_cookie_is_not_secure_locally(client):
    """Plain HTTP in development: a Secure cookie would never come back."""
    response = register_user(client, email="cookie-flags-local@example.com")

    refresh = response.headers["set-cookie"]
    assert "refresh_token=" in refresh
    assert "Secure" not in refresh
