from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, case
from sqlalchemy.exc import SQLAlchemyError
from .db_models import Ticket, Analysis
from .schemas import TicketRequest, TicketAnalysis


def save_ticket(session: Session, ticket: TicketRequest) -> Ticket:
    """Persist a ticket request and return the stored row.

    Raises SQLAlchemyError (after rollback) on DB failures
    such as a duplicate ticket_id.
    """
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


def save_analysis(
        session: Session,
        ticket_id: str,
        analysis: TicketAnalysis | None,
        usage: dict[str, Any],
        success: bool,
        error_message: str | None
        ) -> Analysis:
    """Persist an analysis (or failure record) and return the row.

    Pass analysis=None with success=False to record an LLM
    failure; usage may then be empty. Raises SQLAlchemyError
    (after rollback) on DB failures.
    """
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
        return db_analysis
    except SQLAlchemyError:
        session.rollback()
        raise


def get_ticket_with_analysis(
        session: Session,
        ticket_id: str
) -> dict[str, Ticket | Analysis | None]:
    """Return a ticket with its latest analysis, or None if unknown.

    The latest analysis is ordered by (created_at, id); its value
    is None when the ticket has no analysis row yet.
    """
    ticket = session.scalar(
        select(Ticket).where(Ticket.ticket_id == ticket_id)
    )

    if ticket is None:
        return None

    analysis = session.scalar(
         select(Analysis)
         .where(Analysis.ticket_id == ticket_id)
         .order_by(desc(Analysis.created_at), desc(Analysis.id))
         .limit(1)
    )

    return {
         "ticket": ticket,
         "analysis": analysis
    }


def get_analytics_summary(session: Session) -> dict[str, float | int | None]:
    """Aggregate analysis stats across all stored analyses.

    Averages are None when no analyses exist; totals and counts
    default to 0.0 and 0 respectively.
    """
    analytics_summary = session.execute(
        select(
            func.avg(Analysis.latency_ms).label("average_latency_ms"),
            func.avg(Analysis.total_tokens).label("average_total_tokens"),
            func.sum(Analysis.cost_usd).label("total_cost_usd"),
            func.count(Analysis.id).label("count_of_analyses"),
            func.sum(
                case(
                    (Analysis.success.is_(False), 1),
                    else_=0
                )
            ).label("failed_analyses")
        )
    ).one()

    count_of_analyses = analytics_summary.count_of_analyses or 0
    failed_analyses = analytics_summary.failed_analyses or 0
    average_latency_ms = analytics_summary.average_latency_ms
    average_total_tokens = analytics_summary.average_total_tokens
    total_cost_usd = analytics_summary.total_cost_usd or 0.0
    if count_of_analyses != 0:
        failure_rate = failed_analyses / count_of_analyses
    else:
        failure_rate = 0.0

    return {
          "average_latency_ms": average_latency_ms,
          "average_total_tokens": average_total_tokens,
          "total_cost_usd": total_cost_usd,
          "count_of_analyses": count_of_analyses,
          "failure_rate": failure_rate
    }
