import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


class Ticket(Base):
    """Raw ticket storage."""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class TicketAnalysisRecord(Base):
    """Persisted analysis with cost and latency metadata."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id"), index=True
    )
    category: Mapped[str] = mapped_column(String)
    priority: Mapped[str] = mapped_column(String)
    sentiment: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    suggested_response: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    review_required: Mapped[bool] = mapped_column(Boolean)
    model_used: Mapped[str] = mapped_column(String)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 8)
    )
    latency_ms: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), index=True
    )
