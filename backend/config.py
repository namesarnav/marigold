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
    # session cookie travels in cleartext. Set from the deployed ConfigMap.
    cookie_secure: bool = False

    # --- Public URLs -------------------------------------------------------
    # Where the emailed links point, and where OAuth callbacks bounce the
    # browser back to once the flow finishes.
    frontend_base_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"

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
        """Fill the public-URL settings in from the domain Railway assigns.

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
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if not domain:
            return self

        origin = f"https://{domain}"
        supplied = self.model_fields_set

        if "frontend_base_url" not in supplied:
            self.frontend_base_url = origin
        if "backend_base_url" not in supplied:
            # The API and the bundle are the same service and the same origin,
            # so the OAuth callback host is this one too.
            self.backend_base_url = origin
        if "cookie_secure" not in supplied:
            # Railway terminates TLS in front of the container; the public URL
            # is always https.
            self.cookie_secure = True
        if "cors_origins" not in supplied:
            # Same-origin in this deployment, so this mostly does not come into
            # play — it matters only if a separate frontend is pointed here.
            self.cors_origins = origin

        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
