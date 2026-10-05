from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.analysis_service import analyze_ticket
from app.db import get_db
from app.models import TicketAnalysisRecord
from app.repository import get_ticket_analysis
from app.schemas import (
    Category,
    Priority,
    Sentiment,
    TicketAnalysis,
    TicketAnalysisResponse,
    TicketRequest,
)


router = APIRouter()


def _record_to_response(
    record: TicketAnalysisRecord,
) -> TicketAnalysisResponse:
    """Convert DB record to API response."""
    analysis = TicketAnalysis(
        category=Category(record.category),
        priority=Priority(record.priority),
        sentiment=Sentiment(record.sentiment),
        summary=record.summary,
        suggested_response=record.suggested_response,
        confidence=record.confidence,
        review_required=record.review_required,
    )

    return TicketAnalysisResponse(
        analysis=analysis,
        ticket_id=str(record.ticket_id),
        model_used=record.model_used,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        estimated_cost_usd=float(record.estimated_cost_usd),
        latency_ms=record.latency_ms,
        created_at=record.created_at,
    )


@router.post(
    "/tickets",
    response_model=TicketAnalysisResponse,
    status_code=201,
)
def post_ticket(
    request: TicketRequest,
    db: Session = Depends(get_db),
) -> TicketAnalysisResponse:
    """Create ticket analysis."""
    response = analyze_ticket(
        db=db,
        ticket_text=request.text,
    )

    return response


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketAnalysisResponse,
)
def get_analysis(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> TicketAnalysisResponse:
    """Fetch analysis by ticket id, 404 if not found or bad UUID."""
    try:
        parsed_id = UUID(ticket_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"{ticket_id!r} is not a valid ticket id.",
        )

    record = get_ticket_analysis(
        db=db,
        ticket_id=parsed_id,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for ticket {ticket_id!r}.",
        )

    return _record_to_response(record=record)
