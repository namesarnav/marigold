from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import Base, engine
from .routes import auth, documents, flashcards, quiz, stats

settings = get_settings()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Marigold API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=604800,
    https_only=False,
    same_site="lax",
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(flashcards.router)
app.include_router(quiz.router)
app.include_router(stats.router)
