from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .db_models import Ticket, Analysis
from .schemas import TicketRequest, TicketAnalysis
from .config import settings


def save_ticket(session: Session, ticket: TicketRequest) -> Ticket:
    try:
        db_ticket = Ticket(
            ticket_id=ticket.ticket_id,
            subject=ticket.subject,
            body=ticket.body,
            customer_id=ticket.customer_id
        )
        session.add(db_ticket)
        session.commit()
        session.refresh(db_ticket)
        return db_ticket
    except SQLAlchemyError:
        session.rollback()
        raise


def save_analysis(session: Session, ticket_id: str, analysis: TicketAnalysis | None, usage: dict, success: bool, error_message: str | None) -> Analysis:
    db_analysis = Analysis(
         ticket_id=ticket_id,
         success=success,
         error_message=error_message,
         prompt_tokens=usage.get("prompt_tokens"),
         completion_tokens=usage.get("completion_tokens"),
         total_tokens=usage.get("total_tokens"),
         cost_usd=usage.get("cost_usd"),
         latency_ms=usage.get("latency_ms"),
    )
    if analysis is not None:
         db_analysis.category = analysis.category
         db_analysis.priority = analysis.priority
         db_analysis.sentiment = analysis.sentiment
         db_analysis.summary = analysis.summary
         db_analysis.suggested_response = analysis.suggested_response
         db_analysis.confidence = analysis.confidence
         db_analysis.review_required = analysis.review_required
    try:
        session.add(db_analysis)
        session.commit()
        session.refresh(db_analysis)
    except SQLAlchemyError:
            session.rollback()
            raise
