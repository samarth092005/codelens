from collections.abc import Generator
from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

connect_args: dict[str, Any] = {}
if settings.sync_database_uri.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.sync_database_uri,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and ensures closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
