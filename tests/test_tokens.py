from app.config import settings
from app.tokens import (
    CHAT_OVERHEAD_TOKENS,
    count_tokens,
    estimate_prompt_tokens,
    truncate_to_token_limit,
)

MODEL = settings.openai_model
KNOWN_MODEL = "gpt-4o-mini"


def test_count_tokens_empty() -> None:
    """Empty string has zero tokens."""
    assert count_tokens("", MODEL) == 0


def test_count_tokens_known_strings() -> None:
    """Known strings have expected token counts."""
    assert count_tokens("Hello", MODEL) == 1
    assert count_tokens("Hello world", MODEL) == 2
    assert count_tokens(
        "hello world foo bar baz", MODEL
    ) > count_tokens("hello", MODEL)
    assert count_tokens("repeat", MODEL) == count_tokens(
        "repeat", MODEL
    )


def test_count_tokens_unknown_model_fallback() -> None:
    """Unknown model falls back to base encoding."""
    assert count_tokens(
        "hello", "unknown-model-xyz"
    ) == count_tokens("hello", MODEL)


def test_truncate_no_truncation_when_short() -> None:
    """Short text not truncated when under limit."""
    text = "short ticket text"
    max_tok = count_tokens(text, MODEL) + 5
    assert truncate_to_token_limit(text, max_tok, MODEL) == text


def test_truncate_shortens_overlong_text() -> None:
    """Overlong text truncated to max tokens."""
    long_text = "word " * 5000
    max_tok = 100
    truncated = truncate_to_token_limit(long_text, max_tok, MODEL)
    assert count_tokens(truncated, MODEL) <= max_tok
    assert count_tokens(truncated, MODEL) == max_tok
    assert len(truncated) < len(long_text)
    assert (
        count_tokens(
            truncate_to_token_limit(
                long_text, settings.max_input_tokens, MODEL
            ),
            MODEL,
        )
        <= settings.max_input_tokens
    )


def test_truncate_zero_and_negative() -> None:
    """Zero or negative limit returns empty string."""
    assert truncate_to_token_limit("anything", 0, MODEL) == ""
    assert truncate_to_token_limit("anything", -5, MODEL) == ""


def test_estimate_prompt_tokens_overhead() -> None:
    """Estimate includes chat overhead."""
    sys_p = "system prompt"
    user_p = "user prompt"
    expected = (
        count_tokens(sys_p, MODEL)
        + count_tokens(user_p, MODEL)
        + CHAT_OVERHEAD_TOKENS
    )
    assert estimate_prompt_tokens(sys_p, user_p, MODEL) == expected
    assert estimate_prompt_tokens(
        sys_p, user_p, KNOWN_MODEL
    ) == (
        count_tokens(sys_p, KNOWN_MODEL)
        + count_tokens(user_p, KNOWN_MODEL)
        + 60
    )
