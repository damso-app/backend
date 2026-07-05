from collections.abc import Generator

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


def get_db() -> Generator[Session, None, None]:
    session_factory = create_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
