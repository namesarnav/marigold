import json
from typing import List

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..gemini import generate_flashcards
from ..models import Document, Flashcard, User
from ..schemas import DocumentOut, DocumentPatch, UploadResponse

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


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    try:
        flashcard_data = await generate_flashcards(extracted_text, n=15)
    except Exception as e:
        document.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to generate flashcards: {e}")

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

    document.status = "ready"
    db.commit()

    return UploadResponse(doc_id=document.id)


@router.get("", response_model=List[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
