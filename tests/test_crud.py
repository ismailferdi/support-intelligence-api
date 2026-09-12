import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import MagicMock

from app import crud
from app.db_models import Analysis, Ticket
from app.schemas import TicketAnalysis


def _analysis(**overrides) -> TicketAnalysis:
    base = {
        "category": "billing",
        "priority": "high",
        "sentiment": "negative",
        "summary": "Double charge, refund requested.",
        "suggested_response": "A refund has been issued.",
        "confidence": 0.9,
        "review_required": True,
    }
    base.update(overrides)
    return TicketAnalysis(**base)


def test_save_ticket_persists_retrievable_ticket(test_db_session, sample_ticket):
    crud.save_ticket(test_db_session, sample_ticket)
    row = test_db_session.scalar(
        select(Ticket).where(Ticket.ticket_id == sample_ticket.ticket_id)
    )
    assert row is not None
    assert row.subject == sample_ticket.subject
    assert row.body == sample_ticket.body
    assert row.customer_id == sample_ticket.customer_id


def test_save_analysis_persists_success_and_failure_records(test_db_session, sample_ticket):
    crud.save_ticket(test_db_session, sample_ticket)
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cost_usd": 0.001,
        "latency_ms": 120.0,
    }
    crud.save_analysis(
        test_db_session, sample_ticket.ticket_id, _analysis(),
        usage, True, None,
    )
    ok_row = test_db_session.scalar(
        select(Analysis).where(
            Analysis.ticket_id == sample_ticket.ticket_id,
            Analysis.success.is_(True),
        )
    )
    assert ok_row is not None
    assert ok_row.category == "billing"
    assert ok_row.total_tokens == 150
    assert ok_row.error_message is None

    crud.save_analysis(
        test_db_session, sample_ticket.ticket_id, None,
        {}, False, "boom",
    )
    fail_row = test_db_session.scalar(
        select(Analysis).where(
            Analysis.ticket_id == sample_ticket.ticket_id,
            Analysis.success.is_(False),
        )
    )
    assert fail_row is not None
    assert fail_row.category is None
    assert fail_row.error_message == "boom"


def test_get_analytics_summary_computes_correct_averages(test_db_session, sample_ticket):
    crud.save_ticket(test_db_session, sample_ticket)
    seeds = [
        (100.0, 10, 0.001, True),
        (200.0, 20, 0.002, True),
        (300.0, 30, 0.003, False),
    ]
    for latency_ms, total_tokens, cost_usd, success in seeds:
        crud.save_analysis(
            test_db_session,
            sample_ticket.ticket_id,
            _analysis() if success else None,
            {
                "prompt_tokens": total_tokens,
                "completion_tokens": 0,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
            },
            success,
            None if success else "llm down",
        )

    summary = crud.get_analytics_summary(test_db_session)

    assert summary["count_of_analyses"] == 3
    assert summary["average_latency_ms"] == pytest.approx(200.0)
    assert summary["average_total_tokens"] == pytest.approx(20.0)
    assert summary["total_cost_usd"] == pytest.approx(0.006)
    assert summary["failure_rate"] == pytest.approx(1 / 3)


def test_save_ticket_duplicate_rolls_back_and_reraises(test_db_session, sample_ticket):
    crud.save_ticket(test_db_session, sample_ticket)
    with pytest.raises(SQLAlchemyError):
        crud.save_ticket(test_db_session, sample_ticket)


def test_save_analysis_commit_failure_rolls_back_and_reraises(
    test_db_session, sample_ticket, monkeypatch
):
    crud.save_ticket(test_db_session, sample_ticket)
    monkeypatch.setattr(
        test_db_session, "commit", MagicMock(side_effect=SQLAlchemyError("db down"))
    )
    with pytest.raises(SQLAlchemyError):
        crud.save_analysis(
            test_db_session, sample_ticket.ticket_id, _analysis(),
            {"prompt_tokens": 1}, True, None,
        )


def test_get_ticket_with_analysis_returns_ticket_and_latest(test_db_session, sample_ticket):
    assert crud.get_ticket_with_analysis(test_db_session, "missing") is None
    crud.save_ticket(test_db_session, sample_ticket)
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "cost_usd": 0.001,
        "latency_ms": 50.0,
    }
    crud.save_analysis(test_db_session, sample_ticket.ticket_id, _analysis(), usage, True, None)
    result = crud.get_ticket_with_analysis(test_db_session, sample_ticket.ticket_id)
    assert result["ticket"].ticket_id == sample_ticket.ticket_id
    assert result["analysis"] is not None
    assert result["analysis"].category == "billing"


def test_get_analytics_summary_empty_db(test_db_session):
    summary = crud.get_analytics_summary(test_db_session)
    assert summary["count_of_analyses"] == 0
    assert summary["failure_rate"] == 0.0
    assert summary["total_cost_usd"] == 0.0
