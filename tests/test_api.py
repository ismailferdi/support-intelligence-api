"""API tests against the real FastAPI app.

NOTE: the analyze route is GET /tickets/analyze in code (the spec doc says
POST), and this FastAPI version treats the TicketRequest param as a JSON
*body* on that GET (query params yield 422 "Field required: body") - so these
tests send the ticket as a GET body, matching what the code actually accepts.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app import crud
from app.db import get_session
from app.db_models import Ticket
from app.main import app
from app.schemas import TicketAnalysis


def _canned_result():
    analysis = TicketAnalysis(
        category="billing",
        priority="high",
        sentiment="negative",
        summary="Double charge, refund requested.",
        suggested_response="A refund has been issued.",
        confidence=0.9,
        review_required=True,
    )
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 12.5,
        "cost_usd": 0.001,
    }
    return analysis, usage


@pytest.fixture
def api_client(test_engine, monkeypatch):
    """TestClient with the DB dependency overridden to SQLite and the LLM call mocked."""
    client, mock_analyze = build_client(test_engine, monkeypatch)
    yield client, mock_analyze, test_engine
    app.dependency_overrides.clear()


def build_client(engine, monkeypatch, analyze_mock=None):
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_session():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    mock_analyze = analyze_mock if analyze_mock is not None else MagicMock(
        return_value=_canned_result()
    )
    monkeypatch.setattr(main_module, "analyze_ticket", mock_analyze)
    return TestClient(app), mock_analyze


def test_health_endpoint(api_client):
    client, _, _ = api_client
    assert client.get("/health").json() == {"status": "ok"}


def test_lifespan_startup_runs_init_db(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "init_db", lambda: calls.append(1))
    with TestClient(app):
        pass
    assert calls == [1]


def test_analyze_returns_200_with_well_formed_response(api_client, sample_ticket):
    client, _, _ = api_client
    response = client.request(
        "GET", "/tickets/analyze", json=sample_ticket.model_dump(exclude_none=True)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == sample_ticket.ticket_id
    assert body["analysis"]["category"] == "billing"
    assert body["model_used"]
    assert body["total_tokens"] == 150
    assert body["cost_usd"] == 0.001


def test_analyze_returns_502_when_llm_fails(api_client, sample_ticket):
    client, mock_analyze, _ = api_client
    mock_analyze.side_effect = ValueError("Model returned invalid JSON")
    response = client.request(
        "GET", "/tickets/analyze", json=sample_ticket.model_dump(exclude_none=True)
    )
    assert response.status_code == 502


def test_get_ticket_returns_404_for_unknown_id(api_client):
    client, _, _ = api_client
    assert client.get("/tickets/no-such-ticket").status_code == 404


def test_analytics_summary_returns_expected_shape(api_client, sample_ticket):
    client, _, engine = api_client
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    crud.save_ticket(session, sample_ticket)
    analysis, usage = _canned_result()
    crud.save_analysis(session, sample_ticket.ticket_id, analysis, usage, True, None)
    session.close()

    response = client.get("/analytics/summary")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "average_latency_ms",
        "average_total_tokens",
        "total_cost_usd",
        "count_of_analyses",
        "failure_rate",
    }
    assert body["count_of_analyses"] == 1


def _bare_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_analyze_returns_503_when_ticket_save_fails(monkeypatch, sample_ticket):
    client, _ = build_client(_bare_engine(), monkeypatch)
    try:
        response = client.request(
            "GET", "/tickets/analyze", json=sample_ticket.model_dump(exclude_none=True)
        )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_analyze_returns_503_when_analysis_save_fails(monkeypatch, sample_ticket):
    engine = _bare_engine()
    Ticket.__table__.create(engine)
    client, _ = build_client(engine, monkeypatch)
    try:
        response = client.request(
            "GET", "/tickets/analyze", json=sample_ticket.model_dump(exclude_none=True)
        )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_analyze_returns_503_when_failure_record_save_fails(monkeypatch, sample_ticket):
    engine = _bare_engine()
    Ticket.__table__.create(engine)
    failing = MagicMock(side_effect=ValueError("Model returned invalid JSON"))
    client, _ = build_client(engine, monkeypatch, analyze_mock=failing)
    try:
        response = client.request(
            "GET", "/tickets/analyze", json=sample_ticket.model_dump(exclude_none=True)
        )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
