# AGENTS.md — support-intelligence-api

FastAPI + SQLAlchemy + Alembic ticket-triage service. LLM via OpenAI-compatible `base_url` (currently NVIDIA, see `.env`), not stock OpenAI.

## Setup

- Python 3.12, pinned `requirements.txt`. Use repo venv: `venv/bin/python`, `venv/bin/pytest`, `venv/bin/uvicorn`, `venv/bin/alembic`.
- Env file is required: `app/config.py` loads `<repo>/.env` by absolute path and instantiates `settings = Settings()` at import. Missing vars fail loudly at import.
- Real var names (trust code + `.env.example`, NOT `5-support-intelligence-api.md` which says `OPENROUTER_*`): `OPENAI_API_KEY`, `BASE_URL`, `OPENAI_MODEL`, `DATABASE_URL`, `MAX_INPUT_TOKENS`, `REVIEW_CONFIDENCE_THRESHOLD`. `config.provider` exists but is unused — `llm_client` only reads `openai_model`/`base_url`.
- Importing `app.*` needs a valid env because `app/db.py` calls `get_engine()` at module level (`SessionLocal` binds eagerly). Tests must set `DATABASE_URL` even when mocking the DB.
- `.env` holds a real key and is gitignored — never commit it, print it, or return keys in logs/responses.

## Commands

- Dev server: `venv/bin/uvicorn app.main:app --reload` (`GET /health` → `{"status":"ok"}`).
- Migrations (source of truth for schema beyond dev): `venv/bin/alembic revision --autogenerate -m "..."` / `venv/bin/alembic upgrade head`. `alembic/env.py` uses `settings.database_url` and ignores the `sqlalchemy.url` in `alembic.ini`. App `lifespan` runs `init_db()` (`create_all`) on startup — dev shortcut only.
- Tests: `venv/bin/pytest tests/ -v` — currently collects nothing (`tests/` has only `__init__.py`, `fixtures/` is empty). No `pyproject.toml`, flake8, pytest-cov, CI (`.github/workflows/` empty), or Docker files (`docker/` empty) despite the spec doc describing them.

## Architecture (`app/`)

- `main.py` → `llm_client.analyze_ticket` → `apply_review_rules` → `crud.save_*`. Flow: `save_ticket` first (ticket never lost on LLM failure) → LLM → `save_analysis(success=True/False)`.
- `config.py` singleton; `schemas.py` (TicketRequest/Analysis/Response); `prompt.py` (system/user builders + `TICKET_ANALYSIS_JSON_SCHEMA`); `token_utils.py`; `pricing.py`; `llm_client.py` (module-level `openai.OpenAI` client, tenacity retry); `db_models.py` (`tickets.ticket_id` unique+indexed, `analyses.ticket_id` FK); `db.py`; `crud.py`; `logging_config.py` (module-level `support_api` logger). `warmups/` is scratch — ignore for service changes.

## Gotchas agents miss

- **Analyze route is `GET /tickets/analyze`, not `POST`.** `TicketRequest` is taken as query params. Spec doc says POST — code is truth. Same for `GET /tickets/{ticket_id}`, `GET /analytics/summary`.
- **Pricing-key mismatch:** `MODEL_PRICING` keys are prefixed (`"openai/gpt-oss-20b"`) but `OPENAI_MODEL` is unprefixed (`gpt-oss-20b` in `.env`). `estimate_cost` raises `KeyError` on unlisted models — add the exact `settings.openai_model` string to the table before switching models. `token_utils` has the same shape: `encoding_for_model(model)` falls back to `o200k_harmony`; counts are budgeting approximations, real usage comes from `response.usage`.
- **`save_analysis` never sets `model_used`** (column stays NULL); `main.py` returns `settings.openai_model` in the response instead. Don't read model from the DB.
- **Retry/failure contract:** only `RateLimitError`/`APITimeoutError` retry (5 attempts, exp backoff `multiplier=2, min=2`); bad JSON → `ValueError`, bad schema → `ValidationError`, all surface as HTTP 502 with a `save_analysis(success=False)` row. `analyze_ticket` never returns partial results. Truncation applies to the whole `user_prompt` when `count_tokens > max_input_tokens`.
- **Review rules are deterministic overrides** (`apply_review_rules`, `model_copy`): force `review_required=True` if `confidence < review_confidence_threshold` or (`sentiment == "negative"` and priority in `high`/`urgent`).
- **Logging quirks:** `logging_config.py` adds its `StreamHandler(sys.stdout, "%(asctime)s | %(levelname)s | %(message)s")` unconditionally at import (no `if not logger.handlers` guard) → duplicate lines under `--reload`; it never sets a level, so the logger stays at `WARNING` and `main.py`'s `logger.info` success line (ticket/model/latency/cost/tokens) is suppressed by default. Failure path uses `logger.exception` and does emit. Import it (`from .logging_config import logger`, as `main.py`/`llm_client.py` do) — never `getLogger("support_api")` separately or re-add handlers.
- **Spec doc is stale:** `5-support-intelligence-api.md` describes OpenRouter vars/paths and a roadmap; several Parts (tests, Docker, CI, hardening) are unchecked/not built. Follow executable code.
