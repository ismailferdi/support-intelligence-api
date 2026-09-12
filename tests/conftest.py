"""Shared fixtures for the support-intelligence-api test suite.

All tests run with zero real LLM calls and zero external Postgres dependency:
- the module-level OpenAI-compatible client in app.llm_client is MagicMocked
- the database is an in-memory SQLite engine per test
"""
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db_models import Base
from app.schemas import TicketRequest

CANNED_ANALYSIS = {
    "category": "billing",
    "priority": "high",
    "sentiment": "negative",
    "summary": "Customer was charged twice and wants a refund.",
    "suggested_response": "We are sorry for the double charge - a refund has been issued.",
    "confidence": 0.9,
    "review_required": False,
}


def make_openai_response(payload: dict) -> MagicMock:
    """Build a fake chat.completions response with usage metadata."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    resp.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    return resp


@pytest.fixture
def mock_openai_client(monkeypatch):
    """Patch app.llm_client's module-level OpenAI client (which points at the
    OpenAI-compatible base_url) with a MagicMock returning canned JSON."""
    import app.llm_client as llm_client

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = make_openai_response(CANNED_ANALYSIS)
    monkeypatch.setattr(llm_client, "client", mock_client)
    return mock_client


@pytest.fixture
def priced_model(monkeypatch):
    """Point settings at a model key present in MODEL_PRICING.

    The default OPENAI_MODEL ("gpt-oss-20b") has no exact pricing-table entry
    (keys are "openai/..."-prefixed), so estimate_cost would raise KeyError.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "openai_model", "openai/gpt-oss-20b")
    return settings


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def test_db_session(test_engine):
    TestingSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def sample_ticket():
    return TicketRequest(
        ticket_id="ticket-001",
        subject="Charged twice this month",
        body="I was charged twice on my card and need a refund as soon as possible.",
        customer_id="cust-123",
    )
