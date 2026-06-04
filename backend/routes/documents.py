import json
import logging
from typing import List

import fitz  # PyMuPDF
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..concepts import assign_concepts
from ..database import get_db, get_session_factory
from ..dependencies import get_verified_user
from ..gemini import generate_flashcards
from ..models import Document, Flashcard, User
from ..schemas import DocumentOut, DocumentPatch, UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _extract_text(file_bytes: bytes) -> tuple[str, int]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    full_text = "\n".join(pages).strip()
    return full_text, len(pages)


def _doc_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        filename=d.filename,
        page_count=d.page_count,
        status=d.status,
        created_at=d.created_at.isoformat(),
    )


async def generate_cards_for_document(doc_id: int, user_id: int, session_factory) -> None:
    """Generate a document's flashcards. Runs *after* the upload response is sent.

    Card generation is one Gemini call over the whole extracted text and
    routinely takes tens of seconds on a large PDF. Doing it inside the request
    meant the browser waited on it, and behind the deployed Traefik ingress a
    slow one exceeds the response timeout — the user sees a 504 while the cards
    generate perfectly well on the server.

    Opens its own session, because the request-scoped one is already closed by
    the time this runs. Never raises: a background task has no caller to return
    an error to, so failure is recorded as `status="failed"` on the document,
    which is what the client polls for.
    """
    db = session_factory()
    try:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document is None:
            # Deleted between upload and generation. Nothing to do.
            return

        try:
            flashcard_data = await generate_flashcards(document.extracted_text, n=15)
        except Exception:
            logger.exception("Flashcard generation failed for document %s", doc_id)
            document.status = "failed"
            db.commit()
            return

        new_cards = []
        for item in flashcard_data:
            distractors = item.get("distractors") or []
            card = Flashcard(
                doc_id=document.id,
                question=item.get("question", "").strip(),
                answer=item.get("answer", "").strip(),
                topic=(item.get("topic") or "").strip() or None,
                distractors=json.dumps(distractors[:3]),
            )
            db.add(card)
            new_cards.append(card)

        db.flush()
        assign_concepts(db, new_cards, user_id)

        document.status = "ready"
        db.commit()
    except Exception:
        # Anything unexpected past the Gemini call: still leave the document in a
        # terminal state, or the client polls "processing" forever.
        logger.exception("Unexpected failure processing document %s", doc_id)
        db.rollback()
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document is not None:
            document.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
    session_factory=Depends(get_session_factory),
):
    """Accept a PDF, extract its text, and hand card generation to the background.

    Returns as soon as the document row exists, with `status="processing"`. The
    client polls `GET /api/documents/{doc_id}` until the status becomes `ready`
    or `failed`.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    extracted_text, page_count = _extract_text(content)

    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract text from this PDF.")

    document = Document(
        user_id=current_user.id,
        filename=file.filename,
        status="processing",
        page_count=page_count,
        extracted_text=extracted_text,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(
        generate_cards_for_document, document.id, current_user.id, session_factory
    )

    return UploadResponse(doc_id=document.id, status=document.status)


@router.get("", response_model=List[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [_doc_out(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_out(doc)


@router.patch("/{doc_id}", response_model=DocumentOut)
def rename_document(
    doc_id: int,
    payload: DocumentPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.filename = payload.filename
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
