from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def get_database_url(settings: Settings | None = None) -> str:
    resolved_settings = settings or get_settings()
    if not resolved_settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return resolved_settings.database_url


def create_database_engine(settings: Settings | None = None):
    return create_engine(get_database_url(settings), pool_pre_ping=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=create_database_engine(settings),
    )


@lru_cache
def _default_session_factory() -> sessionmaker[Session]:
    """Process-wide singleton engine/session factory for the production get_db()
    path. Without this, get_db() opened a brand-new engine (and connection pool)
    per request and never disposed it, exhausting Supabase's connection limit
    under sustained traffic (e.g. 2s-interval AI progress polling)."""
    return create_session_factory()


def get_db() -> Generator[Session, None, None]:
    db = _default_session_factory()()
    try:
        yield db
    finally:
        db.close()
