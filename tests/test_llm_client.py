import httpx
import openai
import pytest

from app.exceptions import LLMCallError
from app.llm_client import PRICING, LLMResponse, calculate_cost, call_llm
from app.schemas import RESPONSE_SCHEMA


def test_call_llm_returns_correctly_populated_llmresponse(
    mocker, fake_openai_response
) -> None:
    """call_llm returns LLMResponse with correct fields."""
    mock_resp = fake_openai_response(
        prompt_tokens=12, completion_tokens=25, total_tokens=37
    )
    mocker.patch(
        "app.llm_client._create_completion", return_value=mock_resp
    )

    result = call_llm(
        "system prompt", "user prompt", RESPONSE_SCHEMA, "gpt-oss-20b"
    )

    assert isinstance(result, LLMResponse)
    assert result.raw_content == mock_resp.choices[0].message.content
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 25
    assert result.total_tokens == 37
    assert result.model == "gpt-oss-20b"
    assert result.latency_ms >= 0


def test_call_llm_with_mocker_patch_OpenAI(
    mocker, fake_openai_response
) -> None:
    """Patch OpenAI class as task expects."""
    mock_resp = fake_openai_response(prompt_tokens=5, completion_tokens=10)
    mock_openai_cls = mocker.patch("app.llm_client.OpenAI")
    mocker.patch(
        "app.llm_client._create_completion", return_value=mock_resp
    )

    result = call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")
    assert result.prompt_tokens == 5
    assert mock_openai_cls


def test_calculate_cost() -> None:
    """Cost calculation matches PRICING."""
    cost = calculate_cost(1000, 1000, "gpt-oss-20b")
    expected = (
        PRICING["gpt-oss-20b"][0] * 1000
        + PRICING["gpt-oss-20b"][1] * 1000
    ) / 1000
    assert cost == pytest.approx(expected)
    assert calculate_cost(0, 0, "gpt-oss-20b") == 0.0
    with pytest.raises(KeyError):
        calculate_cost(10, 10, "unknown-model")


def test_call_llm_retries_on_timeout_then_succeeds(
    mocker, fake_openai_response
) -> None:
    """Retries on timeout then succeeds."""
    mocker.patch("time.sleep", return_value=None)
    mock_resp = fake_openai_response(prompt_tokens=10, completion_tokens=20)
    req = httpx.Request(
        "POST", "https://openrouter.ai/api/v1/chat/completions"
    )
    side_effects = [
        openai.APITimeoutError(req),
        openai.APITimeoutError(req),
        mock_resp,
    ]
    mock_create = mocker.patch(
        "app.llm_client.client.chat.completions.create",
        side_effect=side_effects,
    )

    result = call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")

    assert result.prompt_tokens == 10
    assert mock_create.call_count == 3


def test_call_llm_retries_and_raises_after_exhausting(mocker) -> None:
    """Exhaust retries raises LLMCallError."""
    mocker.patch("time.sleep", return_value=None)
    req = httpx.Request(
        "POST", "https://openrouter.ai/api/v1/chat/completions"
    )
    mocker.patch(
        "app.llm_client.client.chat.completions.create",
        side_effect=openai.APITimeoutError(req),
    )

    with pytest.raises(LLMCallError) as exc:
        call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")

    assert "gpt-oss-20b" in str(exc.value)
    from app.llm_client import client

    assert client.chat.completions.create.call_count == 3


def test_call_llm_raises_on_api_connection_error(mocker) -> None:
    """Connection error retries and raises."""
    mocker.patch("time.sleep", return_value=None)
    req = httpx.Request(
        "POST", "https://openrouter.ai/api/v1/chat/completions"
    )
    mocker.patch(
        "app.llm_client.client.chat.completions.create",
        side_effect=openai.APIConnectionError(request=req),
    )
    with pytest.raises(LLMCallError):
        call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")


def test_call_llm_raises_on_empty_content(
    mocker, fake_openai_response
) -> None:
    """Empty content raises LLMCallError."""
    mock_resp = fake_openai_response(
        content="", prompt_tokens=5, completion_tokens=5
    )
    mocker.patch(
        "app.llm_client._create_completion", return_value=mock_resp
    )
    with pytest.raises(LLMCallError, match="empty response"):
        call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")


def test_call_llm_handles_missing_usage(
    mocker, fake_openai_response
) -> None:
    """Missing usage records zero tokens."""
    mock_resp = fake_openai_response(prompt_tokens=10, completion_tokens=10)
    mock_resp.usage = None
    mocker.patch(
        "app.llm_client._create_completion", return_value=mock_resp
    )

    result = call_llm("sys", "user", RESPONSE_SCHEMA, "gpt-oss-20b")
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.total_tokens == 0
