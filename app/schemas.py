from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, Field
from typing import Literal


class TicketRequest(BaseModel):
    ticket_id: str
    subject: str
    body: str
    customer_id: str | None = None

    @field_validator("body")
    @classmethod
    def body_must_not_be_empty(
        cls: type["TicketRequest"], value: str
    ) -> str:
        """Reject empty or whitespace-only ticket bodies."""
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


class TicketResponse(BaseModel):
    """Ticket row shaped for API responses (reads ORM attributes)."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    subject: str
    body: str
    customer_id: str | None = None
    created_at: datetime


class AnalysisResponse(BaseModel):
    """Analysis row shaped for API responses (reads ORM attributes).

    Analysis fields are nullable because failure records store
    NULL analysis columns.
    """

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    category: str | None = None
    priority: str | None = None
    sentiment: str | None = None
    summary: str | None = None
    suggested_response: str | None = None
    confidence: float | None = None
    review_required: bool | None = None
    model_used: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    success: bool | None = None
    error_message: str | None = None
    created_at: datetime


class TicketWithAnalysisResponse(BaseModel):
    """Ticket with its latest analysis, if one exists."""

    ticket: TicketResponse
    analysis: AnalysisResponse | None = None
