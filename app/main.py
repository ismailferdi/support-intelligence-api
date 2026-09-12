from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from openai import APIError
from pydantic import ValidationError
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .db import init_db, get_session
from .schemas import TicketAnalysisResponse, TicketRequest
from .crud import (
    save_ticket,
    save_analysis,
    get_ticket_with_analysis,
    get_analytics_summary,
)
from .llm_client import analyze_ticket, apply_review_rules
from .logging_config import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the database tables on application startup."""
    logger.info("Starting support-intelligence-api")
    init_db()
    yield

app = FastAPI(
    title="Customer Support Intelligence API",
    lifespan=lifespan
)


@app.get('/health', response_model=dict[str, str])
def health() -> dict[str, str]:
    """Report service liveness."""
    return {"status": "ok"}


@app.get('/tickets/analyze', response_model=TicketAnalysisResponse)
def analyze_ticket_endpoint(
        ticket: TicketRequest,
        session: Session = Depends(get_session)
) -> TicketAnalysisResponse:
    """Persist a ticket, analyze it via the LLM, and store the result.

    Raises 503 when the ticket or analysis cannot be written to the
    database, and 502 (after storing a failure record) when the LLM
    analysis itself fails.
    """
    try:
        save_ticket(session, ticket)
    except SQLAlchemyError as exc:
        logger.exception("ticket %s database write failed (save_ticket): %s",
                         ticket.ticket_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable, ticket not saved.",
        ) from exc

    try:
        analysis, usage = analyze_ticket(ticket)
        analysis = apply_review_rules(analysis)

        try:
            save_analysis(
                        session=session,
                        ticket_id=ticket.ticket_id,
                        analysis=analysis,
                        usage=usage,
                        success=True,
                        error_message=None
                    )
        except SQLAlchemyError as exc:
            logger.exception(
                "ticket %s database write failed (save_analysis): %s",
                ticket.ticket_id, exc,
            )
            raise HTTPException(
                status_code=503,
                detail="Database unavailable, analysis not saved.",
            ) from exc

        logger.info(
            "ticket %s analyzed model=%s latency_ms=%.1f "
            "cost_usd=%f total_tokens=%d",
            ticket.ticket_id, settings.openai_model,
            usage["latency_ms"], usage["cost_usd"], usage["total_tokens"],
        )

        return TicketAnalysisResponse(
            ticket_id=ticket.ticket_id,
            analysis=analysis,
            model_used=settings.openai_model,
            latency_ms=usage["latency_ms"],
            total_tokens=usage["total_tokens"],
            cost_usd=usage["cost_usd"]
        )

    except (APIError, ValueError, ValidationError) as exc:
        logger.exception(
            "ticket %s analysis failed: %s", ticket.ticket_id, exc
        )
        try:
            save_analysis(session=session, ticket_id=ticket.ticket_id,
                          analysis=None, usage={}, success=False,
                          error_message=str(exc))
        except SQLAlchemyError as db_exc:
            logger.exception("ticket %s failure-record write failed: %s",
                             ticket.ticket_id, db_exc)
            raise HTTPException(
                status_code=503,
                detail="Database unavailable.",
            ) from db_exc

        raise HTTPException(
            status_code=502,
            detail=f"Ticket analysis failed: {exc}",
        ) from exc


@app.get('/tickets/{ticket_id}', response_model=dict)
def get_ticket_with_analysis_endpoint(
    ticket_id: str,
    session: Session = Depends(get_session)
) -> dict:
    """Fetch a ticket with its latest analysis, or raise 404 if unknown."""
    result = get_ticket_with_analysis(session, ticket_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found."
        )

    return result


@app.get('/analytics/summary', response_model=dict)
def get_analytics_summary_endpoint(
    session: Session = Depends(get_session)
) -> dict:
    """Return aggregate stats across all stored analyses."""
    return get_analytics_summary(session)
