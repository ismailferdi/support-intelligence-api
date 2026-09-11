from contextlib import asynccontextmanager

from openai import APIError
from pydantic import ValidationError
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import init_db, get_session
from .schemas import TicketAnalysisResponse, TicketRequest
from .crud import save_ticket, save_analysis, get_ticket_with_analysis, get_analytics_summary
from .llm_client import analyze_ticket, apply_review_rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Customer Support Intelligence API",
    lifespan=lifespan
)


@app.get('/health', response_model=dict[str, str])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get('/tickets/analyze', response_model=TicketAnalysisResponse)
def analyze_ticket_endpoint(
        ticket: TicketRequest,
        session: Session = Depends(get_session)
) -> TicketAnalysisResponse:
    save_ticket(session, ticket)

    
    try:
        analysis, usage = analyze_ticket(ticket)
        analysis = apply_review_rules(analysis)

        save_analysis(
            session=session,
            ticket_id=ticket.ticket_id,
            analysis=analysis,
            usage=usage,
            success=True,
            error_message=None
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
        save_analysis(
            session=session,
            ticket_id=ticket.ticket_id,
            analysis=None,
            usage={},
            success=False,
            error_message=str(exc),
        )

        raise HTTPException(
            status_code=502,
            detail=f"Ticket analysis failed: {exc}",
        ) from exc


@app.get('/tickets/{ticket_id}', response_model=dict)
def get_ticket_with_analysis_endpoint(
    ticket_id: str,
    session: Session = Depends(get_session)
) -> dict:
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
    return get_analytics_summary(session)