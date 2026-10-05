class LLMCallError(Exception):
    """Raised when LLM call fails after retries."""

    pass


class InvalidAnalysisError(Exception):
    """Raised when LLM output fails schema validation."""

    pass
