import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.analysis_service import analyze_ticket
from app.llm_client import LLMCallError, LLMResponse
from app.schemas import (
    Category,
    Priority,
    Sentiment,
    TicketAnalysis,
    TicketAnalysisResponse,
)


def make_analysis() -> TicketAnalysis:
    """Create sample analysis."""
    return TicketAnalysis(
        category=Category.technical,
        priority=Priority.high,
        sentiment=Sentiment.negative,
        summary="Test summary",
        suggested_response="Test response",
        confidence=0.9,
        review_required=False,
    )


def make_llm_response() -> LLMResponse:
    """Create sample LLMResponse."""
    return LLMResponse(
        raw_content=json.dumps(make_analysis().model_dump(mode="json")),
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        latency_ms=100,
        model="gpt-oss-20b",
    )


def test_analyze_ticket_saves_and_returns(
    mocker, db_session
) -> None:
    """Saves ticket/analysis and returns response."""
    analysis = make_analysis()
    llm_resp = make_llm_response()

    fake_ticket = MagicMock()
    fake_ticket.id = uuid.uuid4()
    fake_ticket.raw_text = "hello ticket"
    fake_ticket.created_at = datetime.now(timezone.utc)

    mock_save_ticket = mocker.patch(
        "app.analysis_service.save_ticket", return_value=fake_ticket
    )
    mock_parse = mocker.patch(
        "app.analysis_service.parse_with_retry",
        return_value=(analysis, llm_resp),
    )

    fake_record = MagicMock()
    fake_record.ticket_id = fake_ticket.id
    fake_record.model_used = llm_resp.model
    fake_record.prompt_tokens = llm_resp.prompt_tokens
    fake_record.completion_tokens = llm_resp.completion_tokens
    fake_record.total_tokens = llm_resp.total_tokens
    fake_record.estimated_cost_usd = 0.001
    fake_record.latency_ms = llm_resp.latency_ms
    fake_record.created_at = datetime.now(timezone.utc)
    fake_record.success = True
    fake_record.error_message = None
    mock_save_analysis = mocker.patch(
        "app.analysis_service.save_analysis", return_value=fake_record
    )
    mocker.patch(
        "app.analysis_service.truncate_to_token_limit",
        side_effect=lambda text, max_tokens, model: text,
    )

    result = analyze_ticket(db=db_session, ticket_text="hello ticket")

    mock_save_ticket.assert_called_once_with(
        db=db_session, text="hello ticket"
    )
    mock_parse.assert_called_once()
    mock_save_analysis.assert_called_once()
    assert mock_save_analysis.call_args.kwargs["success"] is True
    assert (
        mock_save_analysis.call_args.kwargs["error_message"]
        is None
    )
    assert (
        mock_save_analysis.call_args.kwargs["analysis"]
        == analysis
    )

    assert isinstance(result, TicketAnalysisResponse)
    assert result.ticket_id == str(fake_ticket.id)
    assert result.analysis.category == Category.technical
    assert result.prompt_tokens == 10
    assert result.model_used == "gpt-oss-20b"
    assert result.estimated_cost_usd == pytest.approx(0.001)


def test_analyze_ticket_fallback_on_error(
    mocker, db_session
) -> None:
    """LLMCallError fallback uses other/medium/neutral."""
    fake_ticket = MagicMock()
    fake_ticket.id = uuid.uuid4()
    fake_ticket.created_at = datetime.now(timezone.utc)

    mocker.patch(
        "app.analysis_service.save_ticket", return_value=fake_ticket
    )
    mocker.patch(
        "app.analysis_service.parse_with_retry",
        side_effect=LLMCallError("API down"),
    )
    mocker.patch(
        "app.analysis_service.truncate_to_token_limit",
        side_effect=lambda text, max_tokens, model: text,
    )

    fake_record = MagicMock()
    fake_record.ticket_id = fake_ticket.id
    fake_record.model_used = "gpt-oss-20b"
    fake_record.prompt_tokens = 0
    fake_record.completion_tokens = 0
    fake_record.total_tokens = 0
    fake_record.estimated_cost_usd = 0.0
    fake_record.latency_ms = 123
    fake_record.created_at = datetime.now(timezone.utc)
    fake_record.success = False
    fake_record.error_message = "API down"
    mock_save = mocker.patch(
        "app.analysis_service.save_analysis", return_value=fake_record
    )

    result = analyze_ticket(db=db_session, ticket_text="something")

    assert result.analysis.category == Category.other
    assert result.analysis.priority == Priority.medium
    assert result.analysis.confidence == 0.0
    assert result.analysis.review_required is True
    assert result.prompt_tokens == 0
    assert mock_save.call_args.kwargs["success"] is False
    assert "API down" in mock_save.call_args.kwargs["error_message"]
    assert (
        mock_save.call_args.kwargs["analysis"].category
        == Category.other
    )


def test_analyze_ticket_integration_with_real_db(
    mocker, db_session
) -> None:
    """Real DB persistence with mocked LLM."""
    analysis = make_analysis()
    llm_resp = make_llm_response()
    mocker.patch(
        "app.analysis_service.parse_with_retry",
        return_value=(analysis, llm_resp),
    )

    result = analyze_ticket(
        db=db_session, ticket_text="integration test ticket"
    )

    assert isinstance(result, TicketAnalysisResponse)
    assert result.analysis.summary == "Test summary"
    assert result.ticket_id is not None
    from app.repository import get_ticket_analysis
    import uuid as uuid_mod

    record = get_ticket_analysis(
        db_session, uuid_mod.UUID(result.ticket_id)
    )
    assert record is not None
    assert record.category == "technical"
    assert record.success is True
