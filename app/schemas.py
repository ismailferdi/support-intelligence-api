from pydantic import BaseModel, field_validator, Field
from typing import Literal


class TicketRequest(BaseModel):
    ticket_id: str
    subject: str
    body: str
    customer_id: str | None = None

    @field_validator("body")
    @classmethod
    def body_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be empty or whitespace-only.")
        return value


TicketCategory = Literal[
    "billing", "technical", "account", "feature_request", "other"
]
TicketPriority = Literal["low", "medium", "high", "urgent"]
TicketSentiment = Literal["positive", "neutral", "negative"]


class TicketAnalysis(BaseModel):
    category: TicketCategory
    priority: TicketPriority
    sentiment: TicketSentiment
    summary: str
    suggested_response: str
    confidence: float = Field(ge=0.0, le=1.0)
    review_required: bool


class TicketAnalysisResponse(BaseModel):
    ticket_id: str
    analysis: TicketAnalysis
    model_used: str
    latency_ms: float
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
