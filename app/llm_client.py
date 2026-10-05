import logging
import time
from typing import Any

import openai
import tenacity
from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.exceptions import LLMCallError
from app.logging_config import logger


class LLMResponse(BaseModel):
    """Normalized LLM response with usage and latency."""

    raw_content: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    model: str = Field(default="gpt-oss-20b")


# Prices in USD per 1,000 tokens: (input, output).
# Looked up 2026-09-21. OpenAI rates are Standard, short-context,
# from https://developers.openai.com/api/docs/pricing (per-1M / 1000).
# gpt-oss-20b is open-weight and priced by whichever provider serves it;
# the figure below is DeepInfra's (~$0.04 / $0.15 per 1M).
# RE-VERIFY before treating any cost figure as authoritative.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-6-astra": (0.01000, 0.05000),  # $10.00 / $50.00 per 1M
    "gpt-5.6-sol": (0.00400, 0.02000),  # $4.00  / $20.00 per 1M (promo)
    "gpt-5.6-terra": (0.00200, 0.01200),  # $2.00  / $12.00 per 1M
    "gpt-5.6-luna": (0.00020, 0.00120),  # $0.20  / $1.20  per 1M
    "gpt-oss-20b": (0.00004, 0.00015),  # $0.04  / $0.15  per 1M (DeepInfra)
}


def calculate_cost(
    prompt_tokens: int, completion_tokens: int, model: str
) -> float:
    """Calculate USD cost from token counts and PRICING."""
    input_cost, output_cost = PRICING[model]
    return (
        input_cost * prompt_tokens + output_cost * completion_tokens
    ) / 1000


client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.base_url,
    max_retries=0,
)


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    retry=tenacity.retry_if_exception_type(
        (openai.APITimeoutError, openai.APIConnectionError)
    ),
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _create_completion(
    messages: list[dict[str, str]],
    response_schema: dict[str, Any],
    model: str,
) -> Any:
    """Call OpenAI chat completions with retry on timeout/connection."""
    return client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": response_schema,
                "strict": True,
            },
        },
        max_tokens=settings.max_output_tokens,
        timeout=settings.request_timeout_seconds,
        extra_body={"reasoning": {"effort": "low", "exclude": True}},
    )


def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
    model: str,
    additional_messages: list[dict[str, str]] | None = None,
) -> LLMResponse:
    """Call LLM and return normalized usage and latency."""
    start_time = time.perf_counter()
    try:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if additional_messages:
            messages += additional_messages

        response = _create_completion(
            messages=messages,
            response_schema=response_schema,
            model=model,
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else None
        if not content:
            raise LLMCallError(
                f"Model {model!r} returned an empty response."
            )
        if choice.finish_reason == "length":
            logger.warning(
                "LLM output hit token cap (model=%s); JSON maybe truncated",
                model,
            )

        usage = response.usage
        if usage is None:
            logger.warning(
                "No usage data returned (model=%s); recording 0 tokens",
                model,
            )
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        return LLMResponse(
            raw_content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            model=model,
        )

    except openai.APIError as exc:
        logger.error(
            "LLM call failed (model=%s): %s: %s",
            model,
            type(exc).__name__,
            exc,
        )
        raise LLMCallError(
            f"LLM call failed for model {model!r}: {type(exc).__name__}"
        ) from exc
