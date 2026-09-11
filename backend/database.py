from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool
from .config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    pass


if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        # Check a pooled connection is still alive before handing it out. Costs
        # a round trip; without it, any connection the provider closed while
        # idle is handed to whichever request happens to be next and fails
        # there, which makes the error look unrelated to its cause.
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    """The session factory itself, exposed as a FastAPI dependency.

    Background work cannot reuse the request-scoped session from `get_db`: that
    session is closed as soon as the response is sent, and the task runs after
    that. It has to open its own.

    Handing the *factory* out through the dependency system, rather than letting
    background code import `SessionLocal` directly, is what keeps it testable —
    the suite overrides this to point background work at its in-memory engine,
    the same way it already overrides `get_db`.
    """
    return SessionLocal

