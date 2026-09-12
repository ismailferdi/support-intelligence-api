import json

import httpx2
import openai
import pytest
from pydantic import ValidationError

import app.llm_client as llm_client
from app.schemas import TicketAnalysis


def _valid_analysis(**overrides) -> TicketAnalysis:
    base = {
        "category": "technical",
        "priority": "low",
        "sentiment": "neutral",
        "summary": "summary",
        "suggested_response": "response",
        "confidence": 0.9,
        "review_required": False,
    }
    base.update(overrides)
    return TicketAnalysis(**base)


def test_analyze_ticket_returns_valid_analysis(mock_openai_client, priced_model, sample_ticket):
    analysis, usage = llm_client.analyze_ticket(sample_ticket)
    assert isinstance(analysis, TicketAnalysis)
    assert analysis.category == "billing"
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert usage["total_tokens"] == 150
    assert usage["cost_usd"] > 0
    assert usage["latency_ms"] >= 0


def test_analyze_ticket_raises_value_error_on_non_json(mock_openai_client, priced_model, sample_ticket):
    mock_openai_client.chat.completions.create.return_value.choices[0].message.content = (
        "this is not json {"
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        llm_client.analyze_ticket(sample_ticket)


def test_analyze_ticket_raises_validation_error_on_schema_violation(
    mock_openai_client, priced_model, sample_ticket
):
    mock_openai_client.chat.completions.create.return_value.choices[0].message.content = (
        json.dumps({"category": "billing"})
    )
    with pytest.raises(ValidationError):
        llm_client.analyze_ticket(sample_ticket)


def test_analyze_ticket_retries_rate_limit_then_succeeds(
    mock_openai_client, priced_model, sample_ticket
):
    request = httpx2.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx2.Response(429, request=request)
    rate_limit_error = openai.RateLimitError(
        message="rate limited", response=response, body=None
    )
    ok_response = mock_openai_client.chat.completions.create.return_value
    mock_openai_client.chat.completions.create.side_effect = [rate_limit_error, ok_response]

    analysis, _ = llm_client.analyze_ticket(sample_ticket)

    assert analysis.category == "billing"
    assert mock_openai_client.chat.completions.create.call_count == 2


def test_analyze_ticket_truncates_oversized_body(
    mock_openai_client, priced_model, sample_ticket, monkeypatch
):
    from app.config import settings
    from app.token_utils import count_tokens

    monkeypatch.setattr(settings, "max_input_tokens", 30)
    sample_ticket.body = "Refund needed urgently. " * 200

    llm_client.analyze_ticket(sample_ticket)

    sent_messages = mock_openai_client.chat.completions.create.call_args[1]["messages"]
    user_content = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert count_tokens(user_content) <= 30


def test_apply_review_rules_forces_review_on_low_confidence():
    from app.config import settings

    threshold = settings.review_confidence_threshold
    low_confidence = threshold - 0.1 if threshold > 0.1 else 0.0
    analysis = _valid_analysis(confidence=low_confidence, review_required=False)
    assert llm_client.apply_review_rules(analysis).review_required is True


def test_apply_review_rules_forces_review_on_negative_high_priority():
    analysis = _valid_analysis(
        sentiment="negative", priority="high", confidence=0.95, review_required=False
    )
    assert llm_client.apply_review_rules(analysis).review_required is True
