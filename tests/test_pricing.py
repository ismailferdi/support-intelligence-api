import pytest

from app.pricing import MODEL_PRICING, estimate_cost


def test_estimate_cost_computes_expected_value():
    model = "openai/gpt-oss-20b"
    pricing = MODEL_PRICING[model]
    assert estimate_cost(1000, 500, model) == pytest.approx(
        pricing["input_per_1k"] * 1.0 + pricing["output_per_1k"] * 0.5
    )


def test_estimate_cost_raises_for_unpriced_model():
    with pytest.raises(KeyError, match="No pricing configured for model"):
        estimate_cost(10, 10, "no-such-model")
