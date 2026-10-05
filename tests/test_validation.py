import json

import pytest

from app.exceptions import InvalidAnalysisError
from app.llm_client import LLMResponse
from app.schemas import Category, Priority, Sentiment
from app.validation import parse_and_validate, parse_with_retry


def valid_analysis_dict() -> dict:
    """Return valid analysis dict for tests."""
    return {
        "category": "billing",
        "priority": "high",
        "sentiment": "negative",
        "summary": "Customer reports duplicate charge.",
        "suggested_response": "Sorry — refunding.",
        "confidence": 0.95,
        "review_required": False,
    }


def test_parse_and_validate_valid_json() -> None:
    """Valid JSON parses to TicketAnalysis."""
    data = valid_analysis_dict()
    raw = json.dumps(data)
    result = parse_and_validate(raw)
    assert result.category == Category.billing
    assert result.priority == Priority.high
    assert result.sentiment == Sentiment.negative
    assert result.confidence == 0.95
    assert result.review_required is False


def test_parse_and_validate_raises_on_malformed_json() -> None:
    """Malformed JSON raises InvalidAnalysisError."""
    with pytest.raises(InvalidAnalysisError):
        parse_and_validate("not json at all {")

    with pytest.raises(InvalidAnalysisError):
        parse_and_validate('{"category": "billing",}')


def test_parse_and_validate_raises_on_missing_field() -> None:
    """Missing required field raises error."""
    data = valid_analysis_dict()
    del data["summary"]
    with pytest.raises(InvalidAnalysisError):
        parse_and_validate(json.dumps(data))


def test_parse_and_validate_raises_on_invalid_enum() -> None:
    """Invalid enum or out-of-range raises error."""
    data = valid_analysis_dict()
    data["category"] = "not_a_category"
    with pytest.raises(InvalidAnalysisError):
        parse_and_validate(json.dumps(data))

    data = valid_analysis_dict()
    data["confidence"] = 1.5
    with pytest.raises(InvalidAnalysisError):
        parse_and_validate(json.dumps(data))


def test_parse_with_retry_success_first_try(  # noqa: E501
    mocker, fake_openai_response
) -> None:
    """First try success returns analysis."""
    valid_json = json.dumps(valid_analysis_dict())
    mock_resp = fake_openai_response(
        content=valid_json, prompt_tokens=10, completion_tokens=20
    )
    llm_resp = LLMResponse(
        raw_content=mock_resp.choices[0].message.content,
        prompt_tokens=mock_resp.usage.prompt_tokens,
        completion_tokens=mock_resp.usage.completion_tokens,
        total_tokens=mock_resp.usage.total_tokens,
        latency_ms=100,
        model="gpt-oss-20b",
    )
    mocker.patch("app.validation.call_llm", return_value=llm_resp)

    analysis, resp = parse_with_retry("sys", "user", {}, "gpt-oss-20b")

    assert analysis.category == Category.billing
    assert resp.prompt_tokens == 10
    assert resp.total_tokens == 30
    from app.validation import call_llm

    assert call_llm.call_count == 1


def test_parse_with_retry_retry_then_success(mocker) -> None:
    """Invalid first then valid second aggregates tokens."""
    valid = valid_analysis_dict()
    invalid_raw = "not json"
    valid_raw = json.dumps(valid)

    first = LLMResponse(
        raw_content=invalid_raw,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        latency_ms=50,
        model="gpt-oss-20b",
    )
    second = LLMResponse(
        raw_content=valid_raw,
        prompt_tokens=12,
        completion_tokens=15,
        total_tokens=27,
        latency_ms=60,
        model="gpt-oss-20b",
    )
    mock_call = mocker.patch(
        "app.validation.call_llm", side_effect=[first, second]
    )

    analysis, resp = parse_with_retry("sys", "user", {}, "gpt-oss-20b")

    assert analysis.category == Category.billing
    assert resp.prompt_tokens == 22
    assert resp.completion_tokens == 25
    assert resp.total_tokens == 47
    assert resp.latency_ms == 110
    assert mock_call.call_count == 2
    assert mock_call.call_args_list[1].args[4] is not None


def test_parse_with_retry_fallback_on_double_failure(mocker) -> None:
    """Double failure returns fallback analysis."""
    first = LLMResponse(
        raw_content="bad json 1",
        prompt_tokens=5,
        completion_tokens=5,
        total_tokens=10,
        latency_ms=30,
        model="gpt-oss-20b",
    )
    second = LLMResponse(
        raw_content="bad json 2",
        prompt_tokens=7,
        completion_tokens=8,
        total_tokens=15,
        latency_ms=40,
        model="gpt-oss-20b",
    )
    mocker.patch("app.validation.call_llm", side_effect=[first, second])

    analysis, resp = parse_with_retry("sys", "user", {}, "gpt-oss-20b")

    assert analysis.category == Category.other
    assert analysis.priority == Priority.medium
    assert analysis.sentiment == Sentiment.neutral
    assert analysis.confidence == 0.0
    assert analysis.review_required is True
    assert "Automated analysis failed" in analysis.summary
    assert resp.prompt_tokens == 12
    assert resp.total_tokens == 25
