import logging
from typing import List

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
from ..chunking import chunk_pages, extract_pages, strip_nul
from ..config import get_settings
from ..database import get_db, get_session_factory
from ..dependencies import get_verified_user
from ..embeddings import embed_document_chunks
from ..generation import draft_cards, save_cards
from ..gemini import generate_flashcards
from ..models import Document, DocumentChunk, User
from ..schemas import DocumentOut, DocumentPatch, UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


# NUL stripping and per-page extraction live in backend/chunking.py, next to the
# chunker that depends on them. The names below are kept for existing callers.
_strip_nul = strip_nul


def _extract(file_bytes: bytes) -> tuple[str, List[str]]:
    """The document's full text (for full-mode generation) and its pages.

    The full text is the pages joined with newlines, exactly as before
    retrieval existed, so GENERATION_MODE=full sees an unchanged input.
    """
    pages = extract_pages(file_bytes)
    full_text = strip_nul("\n".join(pages)).strip()
    return full_text, pages


def _extract_text(file_bytes: bytes) -> tuple[str, int]:
    full_text, pages = _extract(file_bytes)
    return full_text, len(pages)


def _build_chunks(document_id: int, pages: List[str]) -> List[DocumentChunk]:
    """Chunk rows for a document, without embeddings (those come later)."""
    settings = get_settings()
    return [
        DocumentChunk(
            document_id=document_id,
            chunk_index=c.chunk_index,
            page_start=c.page_start,
            page_end=c.page_end,
            text=c.text,
            token_count=c.token_count,
        )
        for c in chunk_pages(
            pages,
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
    ]


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

    Card generation (one Gemini call over the whole text in full mode; topics,
    retrieval and one call per topic in rag mode) routinely takes tens of
    seconds on a large PDF. Doing it inside the request
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
            await embed_document_chunks(db, document)
            db.commit()
        except Exception:
            # Full-mode generation does not read the vectors, so a failed
            # embedding must not cost the user their cards. The chunks stay,
            # unembedded; rag mode retries the embedding below (and fails the
            # document if it fails again), as does a later regenerate.
            logger.exception("Embedding chunks failed for document %s", doc_id)
            db.rollback()
            document = db.query(Document).filter(Document.id == doc_id).first()
            if document is None:
                return

        try:
            drafted = await draft_cards(db, document, full_generator=generate_flashcards)
        except Exception:
            logger.exception("Flashcard generation failed for document %s", doc_id)
            db.rollback()
            document = db.query(Document).filter(Document.id == doc_id).first()
            if document is not None:
                document.status = "failed"
                db.commit()
            return

        new_cards = save_cards(db, document, drafted.cards)
        assign_concepts(db, new_cards, user_id)
        logger.info(
            "Document %s: %d cards generated in %s mode", doc_id, len(drafted.cards), drafted.mode
        )

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
    extracted_text, pages = _extract(content)

    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract text from this PDF.")

    document = Document(
        user_id=current_user.id,
        filename=file.filename,
        status="processing",
        page_count=len(pages),
        extracted_text=extracted_text,
    )
    db.add(document)
    db.flush()
    # Chunked in the request, in the same transaction as the document: it is
    # local CPU work, and a document should never exist without its chunks.
    # Embedding them is a network call and happens in the background task.
    db.add_all(_build_chunks(document.id, pages))
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
