"""LLM integration for validated support-ticket analysis.

analyze_ticket raises on exhausted API retries, malformed JSON,
schema-validation failures, and pricing errors. It never returns a
partially valid analysis.
"""
import openai
import time
import json
import tenacity
from pydantic import ValidationError

from .config import settings
from .pricing import estimate_cost
from .prompt import (
    TICKET_ANALYSIS_JSON_SCHEMA,
    build_system_prompt,
    build_user_prompt,
)
from .schemas import TicketRequest, TicketAnalysis
from .token_utils import count_tokens, truncate_to_token_limit
from .logging_config import logger


client = openai.OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.base_url
)


@tenacity.retry(
        retry=tenacity.retry_if_exception_type(
            (openai.RateLimitError, openai.APITimeoutError)
        ),
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=2, min=2),
        reraise=True
)
def _complete_completion(messages: list[dict[str, str]]):
    return client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ticket_analysis",
                "schema": TICKET_ANALYSIS_JSON_SCHEMA
            },
        },
    )


def analyze_ticket(ticket: TicketRequest) -> tuple[TicketAnalysis, dict]:
    """Analyze a ticket and return validated output with usage metadata.

    Raises API, JSON parsing, validation, or pricing errors instead of
    returning a partial analysis.
    """
    user_prompt = build_user_prompt(ticket)
    prompt_tokens = count_tokens(user_prompt)
    if prompt_tokens > settings.max_input_tokens:
        logger.warning(
            "Truncating ticket body because prompt token "
            "count %d exceeds limit %d",
            prompt_tokens,
            settings.max_input_tokens
        )
        user_prompt = truncate_to_token_limit(
            user_prompt,
            settings.max_input_tokens
        )
        prompt_tokens = count_tokens(user_prompt)

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]

    start_time = time.perf_counter()
    response = _complete_completion(messages)
    latency_ms = (time.perf_counter() - start_time) * 1000

    raw_content = response.choices[0].message.content

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.error(
            "Invalid JSON response for ticket %s: %r",
            ticket.ticket_id,
            raw_content,
        )
        raise ValueError(
            f"Model returned invalid JSON for ticket {ticket.ticket_id}"
        ) from exc

    try:
        analysis = TicketAnalysis.model_validate(parsed)
    except ValidationError:
        logger.exception(
            "Model response failed schema validation for ticket %s: %r",
            ticket.ticket_id,
            parsed,
        )
        raise

    cost = estimate_cost(
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        settings.openai_model
        )

    usage_metadata = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost
    }

    return analysis, usage_metadata


def apply_review_rules(analysis: TicketAnalysis) -> TicketAnalysis:

    review_required = analysis.review_required

    if analysis.confidence < settings.review_confidence_threshold:
        review_required = True

    if (
        analysis.sentiment == "negative"
        and analysis.priority in ("high", "urgent")
    ):
        review_required = True

    return analysis.model_copy(update={"review_required": review_required})
