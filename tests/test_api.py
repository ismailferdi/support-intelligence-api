import json
import uuid

import pytest

from app.llm_client import LLMResponse
from app.schemas import Category, Priority, Sentiment, TicketAnalysis


def make_analysis(**overrides) -> TicketAnalysis:
    """Create TicketAnalysis with overrides."""
    base = dict(
        category=Category.billing,
        priority=Priority.high,
        sentiment=Sentiment.negative,
        summary="Customer billed twice",
        suggested_response="Refunding",
        confidence=0.95,
        review_required=False,
    )
    base.update(overrides)
    return TicketAnalysis(**base)


def make_llm_response(analysis=None) -> LLMResponse:
    """Create LLMResponse for analysis."""
    if analysis is None:
        analysis = make_analysis()
    return LLMResponse(
        raw_content=json.dumps(analysis.model_dump(mode="json")),
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        latency_ms=100,
        model="gpt-oss-20b",
    )


def test_post_tickets_valid_returns_201_and_shape(
    client, mocker
) -> None:
    """Valid POST returns 201 and correct shape."""
    analysis = make_analysis()
    llm_resp = make_llm_response(analysis)
    mocker.patch(
        "app.analysis_service.parse_with_retry",
        return_value=(analysis, llm_resp),
    )

    resp = client.post("/tickets", json={"text": "I was charged twice"})
    assert resp.status_code == 201
    body = resp.json()
    assert "analysis" in body
    assert "ticket_id" in body
    assert "model_used" in body
    assert "prompt_tokens" in body
    assert "completion_tokens" in body
    assert "total_tokens" in body
    assert "estimated_cost_usd" in body
    assert "latency_ms" in body
    assert "created_at" in body
    assert body["analysis"]["category"] == "billing"
    assert body["analysis"]["confidence"] == 0.95
    uuid.UUID(body["ticket_id"])

    tid = body["ticket_id"]
    get_resp = client.get(f"/tickets/{tid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["ticket_id"] == tid


def test_post_tickets_empty_text_returns_422(client) -> None:
    """Empty text returns 422."""
    resp = client.post("/tickets", json={"text": ""})
    assert resp.status_code == 422
    resp2 = client.post("/tickets", json={})
    assert resp2.status_code == 422


def test_post_tickets_too_long_returns_422(client) -> None:
    """Over 5000 chars returns 422."""
    long_text = "a" * 5001
    resp = client.post("/tickets", json={"text": long_text})
    assert resp.status_code == 422


def test_get_tickets_invalid_uuid_returns_404(client) -> None:
    """Invalid UUID returns 404."""
    resp = client.get("/tickets/not-a-uuid")
    assert resp.status_code == 404
    assert "not a valid ticket id" in resp.json()["detail"]


def test_get_tickets_nonexistent_returns_404(client) -> None:
    """Nonexistent id returns 404."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/tickets/{fake_id}")
    assert resp.status_code == 404
    assert "No analysis found" in resp.json()["detail"]


def test_get_analytics_summary_aggregate_shape(
    client, mocker
) -> None:
    """Analytics aggregates count, latency, cost."""
    analysis1 = make_analysis(category=Category.billing)
    analysis2 = make_analysis(
        category=Category.technical, priority=Priority.low
    )
    mocker.patch(
        "app.analysis_service.parse_with_retry",
        side_effect=[
            (
                analysis1,
                LLMResponse(
                    raw_content="{}",
                    prompt_tokens=10,
                    completion_tokens=10,
                    total_tokens=20,
                    latency_ms=100,
                    model="gpt-oss-20b",
                ),
            ),
            (
                analysis2,
                LLMResponse(
                    raw_content="{}",
                    prompt_tokens=20,
                    completion_tokens=30,
                    total_tokens=50,
                    latency_ms=200,
                    model="gpt-oss-20b",
                ),
            ),
        ],
    )
    client.post("/tickets", json={"text": "ticket 1"})
    client.post("/tickets", json={"text": "ticket 2"})

    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 2
    assert body["avg_latency_ms"] == pytest.approx(150.0)
    assert "total_cost_usd" in body
    assert body["total_cost_usd"] >= 0
    assert body["failure_rate"] == pytest.approx(0.0)

    resp2 = client.get(
        "/analytics/summary", params={"since": "2099-01-01T00:00:00"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["total_requests"] == 0

    resp3 = client.get(
        "/analytics/summary", params={"since": "not-a-date"}
    )
    assert resp3.status_code == 404


def test_get_analytics_summary_with_failure(
    client, mocker
) -> None:
    """Failure rate reflects mocked LLMCallError."""
    from app.exceptions import LLMCallError

    analysis_ok = make_analysis()
    llm_ok = make_llm_response(analysis_ok)

    mocker.patch(
        "app.analysis_service.parse_with_retry",
        side_effect=[(analysis_ok, llm_ok), LLMCallError("down")],
    )
    client.post("/tickets", json={"text": "ok ticket"})
    client.post("/tickets", json={"text": "fail ticket"})

    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    assert resp.json()["total_requests"] == 2
    assert resp.json()["failure_rate"] == pytest.approx(0.5)


def test_health(client) -> None:
    """Health returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
