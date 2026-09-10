from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker
from .config import settings

def get_engine() -> Engine:
    return create_engine(settings.database_url)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=get_engine()
)
