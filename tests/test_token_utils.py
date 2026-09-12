from app.token_utils import count_tokens, truncate_to_token_limit


def test_count_tokens_returns_sensible_positive_int():
    text = "The quick brown fox jumps over the lazy dog. " * 5
    n = count_tokens(text)
    assert isinstance(n, int)
    assert n > 20


def test_truncate_never_exceeds_max_tokens():
    text = "Please refund the duplicate charge on my account. " * 200
    for limit in (1, 10, 100):
        assert count_tokens(truncate_to_token_limit(text, limit)) <= limit
