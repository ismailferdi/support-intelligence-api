from functools import lru_cache

import tiktoken


FALLBACK_ENCODING = "o200k_base"
CHAT_OVERHEAD_TOKENS = 60


@lru_cache(maxsize=32)
def _get_encoding(model: str) -> tiktoken.Encoding:
    """Get tiktoken encoding for model, fall back to base."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding(FALLBACK_ENCODING)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text for the given model."""
    return len(_get_encoding(model).encode(text, disallowed_special=()))


def truncate_to_token_limit(
    text: str, max_tokens: int, model: str
) -> str:
    """Truncate text to at most max_tokens, preserving prefix."""
    enc = _get_encoding(model)
    tokens = enc.encode(text, disallowed_special=())
    max_tokens = max(0, max_tokens)
    if max_tokens == 0:
        return ""
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens]).rstrip("\ufffd")


def estimate_prompt_tokens(
    system_prompt: str, user_prompt: str, model: str
) -> int:
    """Estimate prompt tokens including chat overhead."""
    return (
        count_tokens(system_prompt, model)
        + count_tokens(user_prompt, model)
        + CHAT_OVERHEAD_TOKENS
    )
