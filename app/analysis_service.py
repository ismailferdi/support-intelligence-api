import time

from sqlalchemy.orm import Session

from app.config import settings
from app.llm_client import LLMCallError, LLMResponse
from app.logging_config import logger
from app.prompts import build_system_prompt, build_user_prompt
from app.repository import save_analysis, save_ticket
from app.schemas import (
    RESPONSE_SCHEMA,
    Category,
    Priority,
    Sentiment,
    TicketAnalysis,
    TicketAnalysisResponse,
)
from app.tokens import truncate_to_token_limit
from app.validation import parse_with_retry


def analyze_ticket(
    db: Session, ticket_text: str
) -> TicketAnalysisResponse:
    """Orchestrate ticket saving, LLM analysis, and persistence."""
    ticket = save_ticket(db=db, text=ticket_text)

    ticket_text = truncate_to_token_limit(
        text=ticket_text,
        max_tokens=settings.max_input_tokens,
        model=settings.openai_model,
    )

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(ticket_text=ticket_text)

    start_time = time.perf_counter()
    try:
        analysis, llm_response = parse_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=RESPONSE_SCHEMA,
            model=settings.openai_model,
        )
        success = True
        error_message = None

    except LLMCallError as exc:
        logger.error(
            "LLM call failed for ticket_id=%s: %s", ticket.id, exc
        )
        analysis = TicketAnalysis(
            category=Category.other,
            priority=Priority.medium,
            sentiment=Sentiment.neutral,
            summary=(
                "Automated analysis failed; "
                "this ticket needs manual review."
            ),
            suggested_response="",
            confidence=0.0,
            review_required=True,
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        llm_response = LLMResponse(
            raw_content="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=elapsed_ms,
            model=settings.openai_model,
        )
        success = False
        error_message = str(exc)

    record = save_analysis(
        db=db,
        ticket_id=ticket.id,
        analysis=analysis,
        llm_response=llm_response,
        success=success,
        error_message=error_message,
    )

    logger.info(
        "ticket_id=%s latency_ms=%s prompt_tokens=%s "
        "completion_tokens=%s estimated_cost_usd=%s success=%s",
        record.ticket_id,
        record.latency_ms,
        record.prompt_tokens,
        record.completion_tokens,
        float(record.estimated_cost_usd),
        record.success,
    )

    return TicketAnalysisResponse(
        analysis=analysis,
        ticket_id=str(ticket.id),
        model_used=record.model_used,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        estimated_cost_usd=float(record.estimated_cost_usd),
        latency_ms=record.latency_ms,
        created_at=record.created_at,
    )
