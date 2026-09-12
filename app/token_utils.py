import tiktoken
from .config import settings


def count_tokens(text: str, model: str = settings.openai_model) -> int:
    try:
        encoder = tiktoken.encoding_for_model(model)
    except KeyError:
        encoder = tiktoken.get_encoding('o200k_harmony')

    tokens = encoder.encode(text)

    return len(tokens)


def truncate_to_token_limit(
    text: str, max_tokens: int, model: str = settings.openai_model
) -> str:
    """Bluntly truncate text to a token limit.

    This may cut off text mid-thought. A production system might summarize
    the text instead; truncation is a known simplification here.
    """
    try:
        encoder = tiktoken.encoding_for_model(model)
    except KeyError:
        encoder = tiktoken.get_encoding('o200k_harmony')

    tokens = encoder.encode(text)

    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]

    limited_text = encoder.decode(tokens)
    return limited_text
