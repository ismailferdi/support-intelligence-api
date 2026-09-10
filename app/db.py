from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session
from .config import settings

def get_engine() -> Engine:
    engine: Engine = create_engine(settings.database_url)