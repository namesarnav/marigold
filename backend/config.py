import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str
    database_url: str = "sqlite:///./flashlearn.db"
    cors_origins: str = "http://localhost:5173"
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- Database pool -----------------------------------------------------
    # SQLAlchemy's defaults are 5 connections plus 10 overflow, which is far
    # too small for this workload and fails in a way that looks like an
    # application bug: past 15 concurrent database users every further request
    # blocks for pool_timeout and then returns 500. Measured locally, the API
    # collapsed from ~665 req/s to under 1 req/s at 64 concurrent callers.
    #
    # Sized against the server, not guessed. FastAPI runs `def` endpoints in a
    # threadpool of 40, so 40 is the most concurrent database users one worker
    # can have; 30 covers the realistic peak while leaving headroom under
    # Postgres's default max_connections of 100 once WEB_CONCURRENCY grows.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    # Recycle below any idle timeout the provider imposes. Railway's proxy
    # drops idle connections, and a pooled-but-dead connection surfaces as a
    # random "server closed the connection unexpectedly" on an unrelated
    # request.
    db_pool_recycle: int = 1800

    # --- Logging -----------------------------------------------------------
    # Nothing else configures the root logger, so without this the application's
    # own loggers emit nothing below WARNING: only Python's last-resort handler
    # runs, and it drops INFO entirely. That silently hid two things worth
    # seeing — the console email backend's verification links in development,
    # and background card-generation progress in `kubectl logs`.
    log_level: str = "INFO"

    # --- Cookie security ---------------------------------------------------
    # Sets the Secure flag on the session cookie. False locally (plain HTTP);
    # must be true anywhere the app is reachable over the internet, or the
    # session cookie travels in cleartext. Derived as true from PUBLIC_URL or
    # the Railway domain; see _apply_railway_defaults.
    cookie_secure: bool = False

    # --- Cross-site cookies ------------------------------------------------
    # SameSite on the refresh cookie. Leave it "lax" for the Railway
    # deployment: the frontend's nginx proxies /api, so the browser sees one
    # origin and the cookie is first-party.
    #
    # "none" is only for a frontend that calls this API's own domain directly.
    # Browsers honour it only on a Secure cookie, so the last validator in this
    # class refuses the combination; and Safari blocks such cross-site cookies
    # regardless, which is why the deployment proxies instead.
    cookie_samesite: str = "lax"  # lax | none | strict

    # --- Public URLs -------------------------------------------------------
    # The address people type into the browser. On Railway that is the
    # FRONTEND service's domain, because its nginx proxies /api here — so set,
    # on this service, PUBLIC_URL=https://${{marigold-web.RAILWAY_PUBLIC_DOMAIN}}.
    # One value fills in frontend_base_url, backend_base_url and cors_origins,
    # and turns cookie_secure on for https. Any of those set explicitly still
    # wins. See _apply_railway_defaults.
    public_url: str = ""

    # Where the emailed links point, and where OAuth callbacks bounce the
    # browser back to once the flow finishes.
    frontend_base_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"

    # --- Verification gate -------------------------------------------------
    # Whether an unconfirmed account is blocked from the core features.
    #
    # DISABLED. The gate works by emailing a confirmation link, and no email
    # delivery is configured: EMAIL_BACKEND=console only writes the link to the
    # server log. With the gate on, every password signup would be stuck on
    # "confirm your email" with no email coming.
    #
    # To re-enable: configure EMAIL_BACKEND=ses (see the SES settings below),
    # then swap these two lines back, or set REQUIRE_EMAIL_VERIFICATION=true.
    # The gate itself is intact and the test suite still exercises it.
    #
    # Turning it off does NOT mark anyone verified: `email_verified` still
    # tracks reality, the flag only stops it being enforced. So switching the
    # gate back on returns every account to exactly the state it had.
    # require_email_verification: bool = True
    require_email_verification: bool = False

    # --- Email tokens ------------------------------------------------------
    verification_token_expire_minutes: int = 60 * 24  # 24h; a signup link can wait
    reset_token_expire_minutes: int = 30  # short, per the security requirement

    # --- Rate limiting -----------------------------------------------------
    # Empty means "no Redis configured": the limiter falls back to an in-process
    # store so local dev and tests work. That fallback is per-worker and is NOT
    # safe for multi-process production — set redis_url before deploying.
    redis_url: str = ""
    login_max_attempts_per_account: int = 5
    login_max_attempts_per_ip: int = 20
    login_attempt_window_seconds: int = 900  # 15 min
    resend_verification_max_per_hour: int = 3
    password_reset_max_per_hour: int = 3

    # --- Email sending (AWS SES) -------------------------------------------
    # "ses" sends for real; "console" logs the message instead, which is the
    # default so the app runs end-to-end with no AWS credentials.
    email_backend: str = "console"  # console | ses
    ses_region: str = "us-east-1"
    ses_from_email: str = "no-reply@example.com"
    ses_configuration_set: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # --- OAuth -------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Railway ------------------------------------------------------------
    @model_validator(mode="after")
    def _normalise_database_url(self):
        """Force a Postgres URL onto the psycopg 3 driver.

        SQLAlchemy picks the DBAPI from the URL scheme, and bare
        `postgresql://` means psycopg2 — which is not installed and never will
        be; requirements.txt pins psycopg 3 deliberately. Railway's Postgres
        hands out exactly that bare scheme, so referencing it the documented way
        (`DATABASE_URL=${{Postgres.DATABASE_URL}}`) crashed the container at
        import with `ModuleNotFoundError: No module named 'psycopg2'` — an error
        that names a package nobody put in the file and says nothing about the
        URL that caused it.

        `postgres://` gets the same treatment: SQLAlchemy 2 removed that alias
        outright, and some providers still emit it.
        """
        for prefix in ("postgresql+psycopg://", "postgresql+"):
            # Already carries an explicit driver — the operator chose it, leave
            # it alone.
            if self.database_url.startswith(prefix):
                return self

        for prefix in ("postgresql://", "postgres://"):
            if self.database_url.startswith(prefix):
                self.database_url = (
                    "postgresql+psycopg://" + self.database_url[len(prefix):]
                )
                break

        return self

    @model_validator(mode="after")
    def _apply_railway_defaults(self):
        """Fill the public-URL settings in from PUBLIC_URL or Railway's domain.

        PUBLIC_URL comes first. In the two-service deployment the browser
        talks to the frontend service, whose nginx proxies /api here, so the
        public address is the frontend's domain, not this service's. Deriving
        from this service's own RAILWAY_PUBLIC_DOMAIN there would send OAuth
        callbacks and emailed links to a host that serves only JSON.

        Without PUBLIC_URL this falls back to RAILWAY_PUBLIC_DOMAIN, which is
        right for a single service that serves both halves.

        Railway injects RAILWAY_PUBLIC_DOMAIN (for example
        `marigold-production.up.railway.app`) into every deployment, and it is
        not known until the service exists — so it cannot be committed, and
        hand-copying it into three variables is exactly the kind of setup step
        that gets done once and then forgotten after a rename.

        Three things break quietly when these are left at their localhost
        defaults, and none of them fail at boot:

        * OAuth bounces the browser back to http://localhost:5173 after a
          successful sign-in, on someone else's machine.
        * Verification and password-reset emails link to localhost.
        * cookie_secure stays false, so the session cookie has no Secure flag
          on a site served over HTTPS.

        Anything set explicitly in the environment wins — `model_fields_set`
        holds the fields that were actually supplied, so a custom domain is
        configured the normal way and this never fights it.
        """
        public = self.public_url.strip().rstrip("/")
        if public:
            if not public.startswith(("http://", "https://")):
                raise ValueError(
                    f"PUBLIC_URL must start with https:// or http://, got {self.public_url!r}"
                )
            origin = public
            self.public_url = public
        else:
            domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
            if not domain:
                return self
            origin = f"https://{domain}"

        supplied = self.model_fields_set

        if "frontend_base_url" not in supplied:
            self.frontend_base_url = origin
        if "backend_base_url" not in supplied:
            # The OAuth callback host is the public origin too: the browser
            # reaches this API through it, directly or through the proxy.
            self.backend_base_url = origin
        if "cookie_secure" not in supplied:
            # Railway terminates TLS in front of the container, so its public
            # URLs are https. A plain-http PUBLIC_URL (a local proxy) is not.
            self.cookie_secure = origin.startswith("https://")
        if "cors_origins" not in supplied:
            # The public origin is the only one browsers should send. Behind
            # the proxy requests are same-origin and CORS never comes into
            # play; this only matters if something calls the API cross-origin.
            self.cors_origins = origin

        return self

    @model_validator(mode="after")
    def _check_cookie_samesite(self):
        """Reject a SameSite/Secure combination the browser would discard.

        Deliberately the LAST validator. Pydantic runs after-validators in
        definition order, and cookie_secure is only settled once
        _apply_railway_defaults has derived it. Checked any earlier,
        COOKIE_SAMESITE=none on Railway with COOKIE_SECURE left to derivation
        read the default False and refused to boot a correctly configured
        service.

        `SameSite=None` without `Secure` is ignored by every current browser,
        so the refresh cookie would be dropped on arrival and the only symptom
        would be users being logged out unpredictably. Failing at startup is
        far cheaper to diagnose.
        """
        allowed = {"lax", "none", "strict"}
        value = self.cookie_samesite.lower()
        if value not in allowed:
            raise ValueError(
                f"cookie_samesite must be one of {sorted(allowed)}, got {self.cookie_samesite!r}"
            )
        self.cookie_samesite = value

        if value == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SAMESITE=none requires COOKIE_SECURE=true; browsers "
                "discard a SameSite=None cookie that is not Secure."
            )
        return self


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
