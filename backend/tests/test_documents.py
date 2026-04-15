"""Integration tests for /api/documents/* endpoints."""
import io
from unittest.mock import AsyncMock, patch

from conftest import MOCK_CARDS, register_and_verify, upload_doc


def test_upload_success(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    assert isinstance(doc_id, int)


def test_upload_creates_flashcards(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    resp = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == len(MOCK_CARDS)


def test_upload_non_pdf(client, auth_headers):
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_upload_requires_auth(client, minimal_pdf):
    with patch(
        "backend.routes.documents.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = MOCK_CARDS
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("notes.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
        )
    assert resp.status_code == 401


def test_upload_gemini_failure_marks_failed(client, auth_headers, minimal_pdf):
    with patch(
        "backend.routes.documents.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.side_effect = Exception("Gemini down")
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("notes.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
            headers=auth_headers,
        )
    assert resp.status_code == 500


def test_list_documents_empty(client, auth_headers):
    resp = client.get("/api/documents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_documents_after_upload(client, auth_headers, minimal_pdf):
    upload_doc(client, auth_headers, minimal_pdf, filename="lecture.pdf")
    resp = client.get("/api/documents", headers=auth_headers)
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "lecture.pdf"
    assert docs[0]["status"] == "ready"


def test_list_documents_requires_auth(client):
    resp = client.get("/api/documents")
    assert resp.status_code == 401


def test_get_document_success(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    resp = client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == doc_id
    assert data["page_count"] >= 1


def test_get_document_not_found(client, auth_headers):
    resp = client.get("/api/documents/999", headers=auth_headers)
    assert resp.status_code == 404


def test_rename_document(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    resp = client.patch(
        f"/api/documents/{doc_id}",
        json={"filename": "renamed.pdf"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["filename"] == "renamed.pdf"


def test_rename_not_found(client, auth_headers):
    resp = client.patch(
        "/api/documents/999",
        json={"filename": "x.pdf"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_document(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 204
    # Confirm gone
    assert client.get(f"/api/documents/{doc_id}", headers=auth_headers).status_code == 404


def test_delete_not_found(client, auth_headers):
    resp = client.delete("/api/documents/999", headers=auth_headers)
    assert resp.status_code == 404


def test_other_user_cannot_access_document(client, minimal_pdf):
    # Both users are verified: an unverified account would be rejected by the
    # email-verification gate, which would pass this test for the wrong reason.
    h1 = register_and_verify(client, "u1@x.com", "U1")
    doc_id = upload_doc(client, h1, minimal_pdf)

    h2 = register_and_verify(client, "u2@x.com", "U2")

    # User 2 cannot see user 1's document
    assert client.get(f"/api/documents/{doc_id}", headers=h2).status_code == 404
