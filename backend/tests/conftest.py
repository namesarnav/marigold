import os

# Set env vars BEFORE any backend imports (config uses @lru_cache)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-api-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

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


@pytest.fixture()
def auth_headers(client):
    """Register a test user and return Bearer auth headers."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "tester@example.com", "password": "testpass123", "name": "Tester"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


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
