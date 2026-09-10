from sqlalchemy import create_engine, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

engine = create_engine("postgresql://postgres:postgres@localhost:5432/postgres")

class Base(DeclarativeBase):
    pass

class WarmupNote(Base):
    __tablename__ = "warmup_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(255))


Base.metadata.create_all(engine)

with Session(engine) as session:
    note = WarmupNote(text="SQLAlchemy round trip works")
    session.add(note)
    session.commit()

    saved_note = session.query(WarmupNote).filter_by(id=note.id).one()
    print(saved_note.id, saved_note.text)