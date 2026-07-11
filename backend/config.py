from pydantic_settings import BaseSettings
from functools import lru_cache


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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
