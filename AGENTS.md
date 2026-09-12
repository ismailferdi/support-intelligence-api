# AGENTS.md — support-intelligence-api

FastAPI + SQLAlchemy + Alembic ticket-triage service. LLM via OpenAI-compatible `base_url` (currently NVIDIA, see `.env`), not stock OpenAI.

## Setup

- Python 3.12. Use repo venv: `venv/bin/python`, `venv/bin/pytest`, `venv/bin/uvicorn`, `venv/bin/alembic`.
- Packaging: `pyproject.toml` is source of truth (`[project]` name `support-intelligence-api`, `requires-python >=3.12`; runtime in `dependencies`, pytest/pytest-mock/httpx/flake8 in `dev` extra). `requirements.txt` bundles runtime+test deps and `requirements-dev.txt` holds only flake8 — bump versions in `pyproject.toml` first, then mirror by hand (no generator configured; plain pip has no extras concept).
- Env file is required: `app/config.py` loads `<repo>/.env` by absolute path and instantiates `settings = Settings()` at import. Missing vars fail loudly at import.
- Real var names (trust code + `.env.example` keys, NOT `5-support-intelligence-api.md` which says `OPENROUTER_*`): `OPENAI_API_KEY`, `BASE_URL`, `OPENAI_MODEL`, `DATABASE_URL`, `MAX_INPUT_TOKENS`, `REVIEW_CONFIDENCE_THRESHOLD`. `config.provider` exists but is unused — `llm_client` only reads `openai_model`/`base_url`.
- `OPENAI_MODEL` must exactly match a `MODEL_PRICING` key or `estimate_cost` raises `KeyError`. Keys are `openai/`-prefixed (e.g. `openai/gpt-oss-20b`); bare values like `.env.example`'s `gpt-4` or the config default `gpt-oss-20b` have no entry.
- Importing `app.*` needs a valid env because `app/db.py` calls `get_engine()` at module level (`SessionLocal` binds eagerly). Tests must set `DATABASE_URL` even when mocking the DB.
- `.env` holds a real key and is gitignored — never commit it, print it, or return keys in logs/responses.

## Commands

- Dev server: `venv/bin/uvicorn app.main:app --reload` (`GET /health` → `{"status":"ok"}`).
- Migrations (source of truth for schema beyond dev): `venv/bin/alembic revision --autogenerate -m "..."` / `venv/bin/alembic upgrade head`. `alembic/env.py` uses `settings.database_url` and ignores the `sqlalchemy.url` in `alembic.ini`. App `lifespan` runs `init_db()` (`create_all`) on startup — dev shortcut only.
- Tests: `venv/bin/pytest tests/ -v` — 29 tests, zero external deps (in-memory SQLite via `StaticPool`, mocked LLM). Single test: `venv/bin/pytest tests/test_api.py::<name> -v`. `tests/conftest.py` owns the pattern: `mock_openai_client` patches module-level `llm_client.client`, `priced_model` points `settings.openai_model` at a `MODEL_PRICING` key, API tests override `get_session` + no-op `init_db`. `tests/fixtures/` is still empty.
- Lint: `venv/bin/flake8 app/ tests/` is clean (no flake8 config, default 79-col limit), keep it that way. No CI (`.github/workflows/` empty) despite the spec doc describing it.
- Docker: `docker compose -f docker/docker-compose.yml up -d --build` runs `postgres:16` + `api` (verified working end-to-end; `GET localhost:8000/health` → 200). Build context is repo root (`docker/Dockerfile`: `python:3.12-slim`, `WORKDIR /app`, requirements-first layering, `CMD uvicorn app.main:app 0.0.0.0:8000`); postgres is health-gated (`pg_isready`, `service_healthy`). Fails with `port is already allocated` if a local Postgres holds host 5432 — stop it or remap. `.dockerignore` excludes `venv/ __pycache__/ .git tests/ *.md`. No `/` route exists, so `404` for `/` and `/favicon.ico` in api logs is expected.

## Architecture (`app/`)

- Flow: `main.py` `save_ticket` first (ticket never lost on LLM failure) → `llm_client.analyze_ticket` → `apply_review_rules` → `crud.save_analysis(success=True/False)` (returns the stored row).
- `db_models.py`: `tickets.ticket_id` unique+indexed, `analyses.ticket_id` FK to it. `save_analysis` never sets `model_used` (column stays NULL); `main.py` returns `settings.openai_model` in the response instead. `warmups/` is scratch — ignore for service changes.
- Style: every function in `app/*.py` has a docstring + full hints including returns — keep it that way for new code (`warmups/` exempt).

## Gotchas agents miss

- **Analyze route is `GET /tickets/analyze` with a JSON body — not `POST`, not query params.** `TicketRequest` is declared as a body model, so query strings 422; send `client.request("GET", "/tickets/analyze", json=...)` as `tests/test_api.py` does. Spec doc says POST — code is truth. `/tickets/{ticket_id}` and `/analytics/summary` are plain GETs (no body).
- **Status codes:** LLM failures (bad JSON → `ValueError`, bad schema → `ValidationError`, exhausted retries) → HTTP 502 with a `save_analysis(success=False)` row. DB failures (`SQLAlchemyError` in `save_ticket`/`save_analysis`, incl. duplicate `ticket_id`) → HTTP 503. `analyze_ticket` never returns partial results.
- **Retry:** only `RateLimitError`/`APITimeoutError` retry (5 attempts, exp backoff `multiplier=2, min=2`). Truncation applies to the whole `user_prompt` when `count_tokens > max_input_tokens`.
- **`token_utils` counts are budgeting approximations** (`encoding_for_model` falls back to `o200k_harmony` on `KeyError`); real usage comes from `response.usage`.
- **Review rules are deterministic overrides** (`apply_review_rules`, `model_copy`): force `review_required=True` if `confidence < review_confidence_threshold` or (`sentiment == "negative"` and priority in `high`/`urgent`).
- **Compose api needs its `environment:` DATABASE_URL override** (`@postgres` host): checked-in `.env` uses `localhost`, which inside the api container means itself. `environment:` beats `env_file` — don't remove the block. Same rule for edits: mapping form (`KEY: value`), not list items (`- KEY: value` is rejected); scheme must stay plain `postgresql://` (psycopg2, sync engine) — `+asyncpg` isn't installed and crashes startup.
- **Logging quirks:** `logging_config.py` adds its `StreamHandler(sys.stdout, "%(asctime)s | %(levelname)s | %(message)s")` unconditionally at import (no `if not logger.handlers` guard) → duplicate lines under `--reload`; it never sets a level, so the logger stays at `WARNING` and `main.py`'s `logger.info` success line (ticket/model/latency/cost/tokens) is suppressed by default. Failure path uses `logger.exception` and does emit. Import it (`from .logging_config import logger`, as `main.py`/`llm_client.py` do) — never `getLogger("support_api")` separately or re-add handlers. Service code uses `print()` nowhere (only `warmups/` scratch does).
- **Spec doc is stale:** `5-support-intelligence-api.md` describes OpenRouter vars/paths and a roadmap; later Parts (CI, hardening) are unchecked/not built. Follow executable code.
