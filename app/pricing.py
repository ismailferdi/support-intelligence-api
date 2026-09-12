MODEL_PRICING = {
    "openai/gpt-4.1": {"input_per_1k": 0.002, "output_per_1k": 0.008},
    "openai/gpt-4.1-mini": {"input_per_1k": 0.0004, "output_per_1k": 0.0016},
    "openai/gpt-4.1-nano": {"input_per_1k": 0.0001, "output_per_1k": 0.0004},
    "openai/gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "openai/gpt-5.2": {"input_per_1k": 0.00175, "output_per_1k": 0.014},
    "openai/gpt-5.4": {"input_per_1k": 0.0025, "output_per_1k": 0.015},
    "openai/gpt-5.4-mini": {"input_per_1k": 0.00075, "output_per_1k": 0.0045},
    "openai/gpt-5.4-nano": {"input_per_1k": 0.0002, "output_per_1k": 0.00125},
    "openai/gpt-5.5": {"input_per_1k": 0.005, "output_per_1k": 0.03},
    "openai/gpt-5.6-luna": {"input_per_1k": 0.0002, "output_per_1k": 0.0012},
    "openai/gpt-5.6-luna-pro": {
        "input_per_1k": 0.0002, "output_per_1k": 0.0012
    },
    "openai/gpt-5.6-sol": {"input_per_1k": 0.002, "output_per_1k": 0.01},
    "openai/gpt-5.6-sol-pro": {"input_per_1k": 0.002, "output_per_1k": 0.01},
    "openai/gpt-5.6-terra": {"input_per_1k": 0.002, "output_per_1k": 0.012},
    "openai/gpt-oss-120b": {"input_per_1k": 0.00003, "output_per_1k": 0.00017},
    "openai/gpt-oss-20b": {"input_per_1k": 0.00003, "output_per_1k": 0.00013},
}

# Pricing must be manually kept in sync with provider rates
# and reviewed periodically.


def estimate_cost(
    prompt_tokens: int, completion_tokens: int, model: str
) -> float:
    try:
        pricing = MODEL_PRICING[model]
    except KeyError as exc:
        raise KeyError(
            f"No pricing configured for model: {model}"
        ) from exc

    return (
        prompt_tokens / 1000 * pricing["input_per_1k"]
        + completion_tokens / 1000 * pricing["output_per_1k"]
    )
