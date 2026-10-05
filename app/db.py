from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


def get_db() -> Generator[Session, None, None]:
    """Yield DB session and ensure close."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
