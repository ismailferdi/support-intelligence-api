from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.llm_client import LLMResponse, calculate_cost
from app.models import Ticket, TicketAnalysisRecord
from app.schemas import TicketAnalysis


def save_ticket(db: Session, text: str) -> Ticket:
    """Persist raw ticket and return it."""
    ticket = Ticket(id=uuid4(), raw_text=text)
    try:
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket
    except SQLAlchemyError:
        db.rollback()
        raise


def save_analysis(
    db: Session,
    ticket_id: UUID,
    analysis: TicketAnalysis,
    llm_response: LLMResponse,
    success: bool,
    error_message: str | None,
) -> TicketAnalysisRecord:
    """Persist analysis with token and cost metadata."""
    record = TicketAnalysisRecord(
        id=uuid4(),
        ticket_id=ticket_id,
        category=analysis.category.value,
        priority=analysis.priority.value,
        sentiment=analysis.sentiment.value,
        summary=analysis.summary,
        suggested_response=analysis.suggested_response,
        confidence=analysis.confidence,
        review_required=analysis.review_required,
        model_used=llm_response.model,
        prompt_tokens=llm_response.prompt_tokens,
        completion_tokens=llm_response.completion_tokens,
        total_tokens=llm_response.total_tokens,
        estimated_cost_usd=calculate_cost(
            llm_response.prompt_tokens,
            llm_response.completion_tokens,
            llm_response.model,
        ),
        latency_ms=llm_response.latency_ms,
        success=success,
        error_message=error_message,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except SQLAlchemyError:
        db.rollback()
        raise


def get_ticket_analysis(
    db: Session, ticket_id: UUID
) -> TicketAnalysisRecord | None:
    """Fetch latest analysis for ticket id."""
    stmt = (
        select(TicketAnalysisRecord)
        .where(TicketAnalysisRecord.ticket_id == ticket_id)
        .order_by(TicketAnalysisRecord.created_at.desc())
        .limit(1)
    )
    return db.scalars(statement=stmt).first()


def get_analytics_summary(
    db: Session, since: datetime | None = None
) -> dict[str, float | int]:
    """Aggregate request count, latency, cost, and failure rate."""
    stmt = select(
        func.count(TicketAnalysisRecord.id),
        func.avg(TicketAnalysisRecord.latency_ms),
        func.coalesce(func.sum(TicketAnalysisRecord.estimated_cost_usd), 0),
        func.count(TicketAnalysisRecord.id).filter(
            TicketAnalysisRecord.success.is_(False)
        ),
    )
    if since is not None:
        stmt = stmt.where(TicketAnalysisRecord.created_at >= since)

    total, avg_latency, total_cost, failures = db.execute(stmt).one()
    return {
        "total_requests": total,
        "avg_latency_ms": float(avg_latency)
        if avg_latency is not None
        else 0.0,
        "total_cost_usd": float(total_cost),
        "failure_rate": failures / total if total else 0.0,
    }
