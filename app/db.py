from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from collections.abc import Generator
from .config import settings

def get_engine() -> Engine:
    return create_engine(settings.database_url)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=get_engine()
)

def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
