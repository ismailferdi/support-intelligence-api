from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Category(Enum):
    """Ticket category values."""

    billing = "billing"
    technical = "technical"
    account = "account"
    feature_request = "feature_request"
    other = "other"


class Priority(Enum):
    """Ticket priority values."""

    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class Sentiment(Enum):
    """Ticket sentiment values."""

    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class TicketRequest(BaseModel):
    """Incoming ticket request."""

    text: str

    @field_validator("text")
    @classmethod
    def validate_text_length(cls: Any, value: str) -> str:
        """Validate text is non-empty and <=5000 chars."""
        if len(value) == 0:
            raise ValueError("The text should not be empty")
        if len(value) > 5000:
            raise ValueError("The text is so long")
        return value


class TicketAnalysis(BaseModel):
    """Validated LLM analysis output."""

    category: Category
    priority: Priority
    sentiment: Sentiment
    summary: str
    suggested_response: str
    confidence: float = Field(ge=0.0, le=1.0)
    review_required: bool


class TicketAnalysisResponse(BaseModel):
    """Analysis plus persisted metadata returned to client."""

    analysis: TicketAnalysis
    ticket_id: str
    model_used: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    created_at: datetime


RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "billing",
                "technical",
                "account",
                "feature_request",
                "other",
            ],
        },
        "priority": {
            "type": "string",
            "enum": ["low", "medium", "high", "urgent"],
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative"],
        },
        "summary": {"type": "string"},
        "suggested_response": {"type": "string"},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "review_required": {"type": "boolean"},
    },
    "required": [
        "category",
        "priority",
        "sentiment",
        "summary",
        "suggested_response",
        "confidence",
        "review_required",
    ],
    "additionalProperties": False,
}
