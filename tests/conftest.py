import json

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.models import Base
from app.main import app
from app.db import get_db
from app.schemas import Category, Priority, Sentiment

TEST_DB_URL = "sqlite://"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    conn = test_engine.connect()
    trans = conn.begin()
    TestingSession = sessionmaker(bind=conn, expire_on_commit=False)
    session = TestingSession()
    yield session
    session.close()
    trans.rollback()
    conn.close()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db(db_session):
    return db_session


@pytest.fixture
def fake_openai_response():
    def _make(
        content: str | dict | None = None,
        prompt_tokens: int = 42,
        completion_tokens: int = 38,
        total_tokens: int | None = None,
        finish_reason: str = "stop",
    ):
        if content is None:
            content = json.dumps(
                {
                    "category": Category.billing.value,
                    "priority": Priority.high.value,
                    "sentiment": Sentiment.negative.value,
                    "summary": "Customer reports duplicate charge.",
                    "suggested_response": "Sorry — refunding the duplicate.",
                    "confidence": 0.95,
                    "review_required": False,
                }
            )
        elif isinstance(content, dict):
            content = json.dumps(content)

        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens

        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_choice.finish_reason = finish_reason
        mock_choice.message.role = "assistant"
        mock_resp.choices = [mock_choice]
        mock_resp.usage = MagicMock(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        mock_resp.id = "chatcmpl-test-123"
        mock_resp.model = "gpt-oss-20b"
        mock_resp.object = "chat.completion"
        return mock_resp

    return _make


# aliases for typo in earlier version
@pytest.fixture
def fake_openai_reponse(fake_openai_response):
    return fake_openai_response


@pytest.fixture
def fake_opnenai_response_json(fake_openai_response):
    return fake_openai_response().choices[0].message.content


@pytest.fixture
def fake_openai_response_json(fake_openai_response):
    return fake_openai_response().choices[0].message.content
