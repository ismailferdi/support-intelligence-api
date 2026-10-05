import pydantic

from app.exceptions import InvalidAnalysisError
from app.llm_client import LLMResponse, call_llm
from app.logging_config import logger
from app.schemas import Category, Priority, Sentiment, TicketAnalysis


def parse_and_validate(raw_content: str) -> TicketAnalysis:
    """Parse raw JSON string into validated TicketAnalysis."""
    try:
        return TicketAnalysis.model_validate_json(raw_content)
    except pydantic.ValidationError as exc:
        raise InvalidAnalysisError(
            f"{type(exc).__name__}: {exc}"
        ) from exc


def parse_with_retry(
    system_prompt: str,
    user_prompt: str,
    response_schema: dict,
    model: str,
) -> tuple[TicketAnalysis, LLMResponse]:
    """Call LLM, validate, retry once with correction, else fallback."""
    first = call_llm(
        system_prompt,
        user_prompt,
        response_schema,
        model,
    )

    try:
        return parse_and_validate(first.raw_content), first
    except InvalidAnalysisError as exc:
        logger.warning(
            "Analysis failed validation (model=%s); retrying once",
            model,
        )
        correction = [
            {"role": "assistant", "content": first.raw_content},
            {
                "role": "user",
                "content": (
                    "Your previous output didn't match the required schema:\n"
                    f"{str(exc)[:1000]}\n"
                    "Return corrected JSON that matches the schema exactly."
                ),
            },
        ]

    second = call_llm(
        system_prompt,
        user_prompt,
        response_schema,
        model,
        correction,
    )

    second.prompt_tokens += first.prompt_tokens
    second.completion_tokens += first.completion_tokens
    second.total_tokens += first.total_tokens
    second.latency_ms += first.latency_ms

    try:
        return parse_and_validate(second.raw_content), second
    except InvalidAnalysisError:
        logger.warning(
            "Analysis failed validation twice (model=%s); using fallback",
            model,
        )
        return TicketAnalysis(
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
        ), second
