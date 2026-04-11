import os

# Set env vars BEFORE any backend imports (config uses @lru_cache)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-api-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
# Console email backend + no Redis: the suite exercises the real flows
# without AWS or a running Redis. OAuth creds are placeholders so both
# providers register and the routes are reachable.
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:5173")
os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8000")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-github-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-github-client-secret")

import io

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Clear lru_cache so our env vars take effect before backend modules read config
from backend.config import get_settings

get_settings.cache_clear()

from backend.database import Base, get_db
from backend.main import app

# Isolated in-memory SQLite engine shared across all connections in a test
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

MOCK_CARDS = [
    {
        "question": "What is Python?",
        "answer": "A high-level programming language",
        "topic": "Python",
        "distractors": ["Java", "C++", "Rust"],
    },
    {
        "question": "What do variables store?",
        "answer": "Data values",
        "topic": "Python",
        "distractors": ["Functions", "Classes", "Modules"],
    },
    {
        "question": "What are functions?",
        "answer": "Reusable code blocks",
        "topic": "Python",
        "distractors": ["Variables", "Classes", "Lists"],
    },
]


@pytest.fixture(autouse=True)
def _reset_db():
    """Create all tables before each test, drop them after."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def client():
    def _override_get_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# Meets the server-side policy in backend/security.py: 12+ chars, three
# character classes, not a common password, not derived from the email.
STRONG_PASSWORD = "Str0ng-Pass!2024"


@pytest.fixture(autouse=True)
def _reset_auth_side_state():
    """Clear the outbox and the rate-limit counters between tests.

    Both are process-global. Without this, one test's failed logins would eat
    another's budget and the console outbox would accumulate across the suite,
    making tests order-dependent.
    """
    from backend.mailer import SENT_EMAILS
    from backend.ratelimit import get_limiter

    SENT_EMAILS.clear()
    get_limiter().clear()
    yield
    SENT_EMAILS.clear()
    get_limiter().clear()


def register_user(client, email="tester@example.com", password=STRONG_PASSWORD, name="Tester"):
    """Register and return the raw response."""
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def latest_email_to(email):
    """The most recent console-backend email sent to `email`, or None."""
    from backend.mailer import SENT_EMAILS

    for message in reversed(SENT_EMAILS):
        if message.to == email:
            return message
    return None


def token_from_link(message, path):
    """Pull the `token` query param out of the link in an email body.

    Tests read the token out of the delivered message rather than the database,
    so they assert on what the user actually receives.
    """
    import re
    from urllib.parse import parse_qs, urlparse

    match = re.search(rf"https?://\S*{re.escape(path)}\?token=(\S+)", message.text_body)
    assert match, f"no {path} link in email body:\n{message.text_body}"
    return parse_qs(urlparse(match.group(0)).query)["token"][0]


def verify_user(client, email):
    """Complete email verification for `email` by using the emailed link."""
    message = latest_email_to(email)
    assert message is not None, f"no verification email sent to {email}"
    token = token_from_link(message, "/verify-email")
    resp = client.post("/api/auth/verify-email", json={"token": token})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def register_and_verify(client, email, name="User", password=STRONG_PASSWORD):
    """Register a user, verify their email, return Bearer headers for them.

    Cookies are cleared afterwards on purpose: `get_current_user` resolves the
    session cookie before the Authorization header, so leaving the registration
    cookie in place would make every later request resolve as the most recently
    registered user regardless of the token sent.
    """
    resp = register_user(client, email=email, password=password, name=name)
    assert resp.status_code == 200, resp.text
    token = verify_user(client, email)
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def unverified_auth_headers(client):
    """A registered but NOT email-verified user. Core features must reject it."""
    resp = register_user(client, email="unverified@example.com", name="Unverified")
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_verified"] is False
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def db_session():
    """A plain SQLAlchemy session on the test engine.

    Lets the OAuth linking logic be exercised as the pure function it is,
    without standing up an HTTP round trip through a provider.
    """
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def auth_headers(client):
    """Register a test user, verify their email, return Bearer auth headers.

    Verification is part of the fixture because every core endpoint now sits
    behind `get_verified_user`; an unverified token would 403 everywhere.
    """
    resp = register_user(client)
    assert resp.status_code == 200, resp.text
    token = verify_user(client, "tester@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def minimal_pdf():
    """A small valid PDF with extractable text for upload tests."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        (
            "Python is a high-level programming language. "
            "Variables store data values. "
            "Functions are reusable code blocks. "
            "Classes support object-oriented programming. "
            "Lists store ordered collections of items."
        ),
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def upload_doc(client, headers, pdf_bytes, filename="notes.pdf"):
    """Helper: upload a PDF with mocked Gemini, return doc_id."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routes.documents.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = MOCK_CARDS
        resp = client.post(
            "/api/documents/upload",
            files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["doc_id"]
