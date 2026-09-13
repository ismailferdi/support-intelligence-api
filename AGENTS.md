# AGENTS.md — support-intelligence-api

FastAPI + SQLAlchemy + Alembic ticket-triage service. LLM via OpenAI-compatible `base_url` (currently NVIDIA, see `.env`), not stock OpenAI.

## Setup

- Python 3.12. Use repo venv: `venv/bin/python`, `venv/bin/pytest`, `venv/bin/uvicorn`, `venv/bin/alembic`.
- `pyproject.toml` is source of truth (`requires-python >=3.12`); mirror version bumps into `requirements.txt` / `requirements-dev.txt` by hand (no generator).
- Env file is required: `app/config.py` loads `<repo>/.env` by absolute path, `settings = Settings()` at import. Missing vars fail loudly.
- Real var names (trust code + `.env.example`, NOT `5-support-intelligence-api.md` which says `OPENROUTER_*`): `OPENAI_API_KEY`, `BASE_URL`, `OPENAI_MODEL`, `DATABASE_URL`, `MAX_INPUT_TOKENS`, `REVIEW_CONFIDENCE_THRESHOLD`. `config.provider` is unused.
- `OPENAI_MODEL` must exactly match a `MODEL_PRICING` key or `estimate_cost` raises `KeyError`. Keys are `openai/`-prefixed (e.g. `openai/gpt-oss-20b`); bare values like `.env.example`'s `gpt-4` or the config default `gpt-oss-20b` have no entry.
- `app/db.py` calls `get_engine()` at module level, so importing `app.*` needs a valid `DATABASE_URL` even when tests mock the DB.
- `.env` holds a real key and is gitignored — never commit, print, or echo it.

## Commands

- Dev server: `venv/bin/uvicorn app.main:app --reload` (`GET /health` → `{"status":"ok"}`).
- Migrations are schema source of truth beyond dev: `venv/bin/alembic revision --autogenerate -m "..."` / `venv/bin/alembic upgrade head`. `alembic/env.py` uses `settings.database_url`, ignores `alembic.ini`'s `sqlalchemy.url`. App `lifespan` runs `init_db()` (`create_all`) — dev shortcut only.
- Tests: `venv/bin/pytest tests/ -v` — 31 tests, zero external deps (in-memory SQLite via `StaticPool`, mocked LLM). Single test: `venv/bin/pytest tests/test_api.py::<name> -v`. `tests/conftest.py` owns the pattern: `mock_openai_client` patches module-level `llm_client.client`, `priced_model` points `settings.openai_model` at a `MODEL_PRICING` key, API tests override `get_session` + no-op `init_db`.
- Lint: `venv/bin/flake8 app/ tests/` is clean (no flake8 config, default 79-col limit). `.github/workflows/ci.yml` exists but is empty — no CI runs.
- Docker: `docker compose -f docker/docker-compose.yml up -d --build` (postgres:16 + api, postgres health-gated via `pg_isready`). Fails with `port is already allocated` if a local Postgres holds host 5432. No `/` route exists, so `404` for `/` and `/favicon.ico` in api logs is expected.

## Architecture (`app/`)

- Flow: `main.py` `save_ticket` first (ticket never lost on LLM failure) → `llm_client.analyze_ticket` → `apply_review_rules` → `crud.save_analysis(success=True/False)`.
- `db_models.py`: `tickets.ticket_id` unique+indexed, `analyses.ticket_id` FK to it. `save_analysis` never sets `model_used` (column stays NULL); `main.py` returns `settings.openai_model` in the response instead. `warmups/` is scratch — ignore for service changes.
- Style: every function in `app/*.py` has a docstring + full hints including returns — keep it that way (`warmups/` exempt).

## Gotchas agents miss

- **Analyze route is `GET /tickets/analyze` with a JSON body — not `POST`, not query params.** Query strings 422; send `client.request("GET", "/tickets/analyze", json=...)` as `tests/test_api.py` does. Spec doc says POST — code is truth.
- **Status codes:** LLM failures (bad JSON → `ValueError`, bad schema → `ValidationError`, exhausted retries) → 502 with a `save_analysis(success=False)` row. DB failures (`SQLAlchemyError` in `save_ticket`/`save_analysis`, incl. duplicate `ticket_id`) → 503. `analyze_ticket` never returns partial results.
- **Retry:** only `RateLimitError`/`APITimeoutError` retry (5 attempts, exp backoff `multiplier=2, min=2`). Truncation applies to the whole `user_prompt` when `count_tokens > max_input_tokens`.
- **`token_utils` counts are budgeting approximations** (`encoding_for_model` falls back to `o200k_harmony` on `KeyError`); real usage comes from `response.usage`.
- **Review rules are deterministic overrides** (`apply_review_rules`, `model_copy`): force `review_required=True` if `confidence < review_confidence_threshold` or (`sentiment == "negative"` and priority in `high`/`urgent`).
- **Compose api needs its `environment:` DATABASE_URL override** (`@postgres` host): `.env` uses `localhost`, which inside the container means itself. `environment:` beats `env_file` — don't remove it. Keep mapping form (`KEY: value`, not `- KEY: value`) and plain `postgresql://` scheme (sync psycopg2 engine; `+asyncpg` isn't installed).
- **Logging:** `logging_config.py` adds its `StreamHandler` unconditionally at import (no guard) → duplicate lines under `--reload`; it never sets a level, so the logger stays at `WARNING` and `main.py`'s `logger.info` success line is suppressed (failures use `logger.exception` and do emit). Import `from .logging_config import logger` — never `getLogger` separately or re-add handlers. Service code uses `print()` nowhere (only `warmups/` does).
- **Spec doc is stale:** `5-support-intelligence-api.md` describes OpenRouter vars/paths and unchecked roadmap parts (CI, hardening); it is also gitignored. Follow executable code.
