# AGENTS.md - support-intelligence-api

Small FastAPI service: `POST /tickets` analyzes a raw support ticket via OpenRouter/OpenAI and returns validated JSON + cost/latency metadata stored in Postgres. Entrypoint is `app.main:app` (root `main.py` is a placeholder). CI: `.github/workflows/ci.yml` (pytest `--cov`, flake8, docker build).

## Setup

- Toolchain is `uv` (`requires-python >=3.12`). Install with `uv sync`, run everything with `uv run ...`. Test/lint deps live in **both** `requirements-dev.txt` and the pyproject `dev` group — pip-based CI uses the former, `uv` the latter; keep them in sync when adding anything (both now include `pytest`, `pytest-cov`).
- Env loads from repo-root `.env` via `app/config.py` (`settings`, `engine`, and the OpenAI `client` are all created at import, so env changes need a restart/reimport). Required: `OPENAI_API_KEY`, `DATABASE_URL`, `POSTGRES_USER/PASSWORD/DB`.
- `.env.example` has two traps: `OPENAI_APY_KEY` typo (real key is `OPENAI_API_KEY`), and `OPENAI_MODEL=openai/gpt-oss-20b` which does **not** match any `PRICING` key in `app/llm_client.py` — `calculate_cost()` does `PRICING[model]` and will `KeyError`. Use the bare form (`gpt-oss-20b`, as in the current `.env`). The `DATABASE_URL` default in `app/config.py` is a dummy non-`psycopg` URL, so a real `DATABASE_URL` (`postgresql+psycopg://...`) is mandatory. `.env` holds a real key and is gitignored — never commit it.
- Dev DB only: `docker compose -f docker/docker-compose.dev.yml up -d` (service `database`, port `5432`).
- Full stack: `docker compose --env-file .env -f docker/docker-compose.yml up --build`, then `... exec api python -m scripts.create_tables` (`scripts/` is `COPY`'d into the image). `--env-file .env` is mandatory: the project dir defaults to `docker/`, so the repo-root `.env` is otherwise ignored for `${...}` interpolation (do **not** substitute `--project-directory .` — it re-bases relative paths and breaks the postgres `env_file: ../.env`). `environment:` must be a mapping (or `KEY=VAL` strings); `- KEY: value` list-of-maps fails to parse. The PG18 image requires the volume at `pgdata:/var/lib/postgresql` (no `/data` suffix or postgres exits 1). Both compose files share the `docker_pgdata` volume — never `down -v` or delete it casually. The API runs from the image, not the working tree: code edits need rebuild plus `--force-recreate api`.
- Create tables only as a module: `uv run python -m scripts.create_tables`. Reset needs both flags non-interactively: `--reset --yes` (bare `--reset` prompts and dies with EOF in CI).

## Run & verify

- Dev server: `uv run uvicorn app.main:app --reload` (`/docs`, `/health`).
- Single test: `uv run pytest tests/test_tokens.py -v`. Full suite: `uv run pytest tests/ -v` (CI appends `--cov=app --cov-report=term-missing`). Lint: `uv run flake8 app/ tests/` (no config file; currently clean).
- Tests need no Postgres or API key: `tests/conftest.py` uses in-memory SQLite (StaticPool, FK pragma, per-test rollback) and overrides `get_db`. Never call the real LLM in tests — mock `app.analysis_service.parse_with_retry` for API/service tests, or `app.llm_client._create_completion` / `client.chat.completions.create` for retry tests. `fake_openai_response` factory builds the mock Chat Completions object.
- CI needs **dummy** env (`OPENAI_API_KEY`, `OPENAI_MODEL=gpt-oss-20b`, `DATABASE_URL`, `POSTGRES_*` — see `ci.yml`) because `Settings()` validates at import and collection crashes without them; no services or secrets since tests never touch the network.

## Architecture

`POST /tickets` (`app/routers/tickets.py`) → `analyze_ticket()` (`app/analysis_service.py`, the only place with business logic — keep routers thin) → `save_ticket()` first, `truncate_to_token_limit()` to `MAX_INPUT_TOKENS`, prompts (`app/prompts.py`), `parse_with_retry()` (`app/validation.py`: exactly one retry with correction text, token/latency summed across attempts) → `call_llm()` (`app/llm_client.py`) → `save_analysis()` (`app/repository.py`).

## Gotchas

- `_create_completion()` sends `extra_body={"reasoning": {"effort": "low", "exclude": True}}` — load-bearing, do not remove. Without it, `gpt-oss-20b` via OpenRouter spends the budget in the reasoning channel (~99 reasoning tokens) and returns `content=None` with `finish: stop`, so **every** request degrades to the placeholder (`failure_rate` 1.0). Verified symptom: `LLM call failed ... returned an empty response` with zero tokens and ~10s latency.
- `POST /tickets` returns `201`; `text` must be 1–5000 chars else `422`.
- `GET /tickets/{id}` returns `404` for both bad-UUID format and not-found. `GET /analytics/summary?since=<ISO>` returns `404` (not `422`) on unparseable `since` (`datetime.fromisoformat`).
- Retries: tenacity retries 3x exponential backoff **only** on `APITimeoutError`/`APIConnectionError`; SDK retries disabled (`max_retries=0`). Content/validation errors never retry at this layer.
- Failure policy: double validation failure **or** `LLMCallError` → placeholder `TicketAnalysis(other/medium/neutral, confidence=0.0, review_required=True)`; `LLMCallError` path records `success=False` with zero tokens. API never 500s for these — `LLMCallError` maps to `502`, catch-all `Exception` to `500` without leaking tracebacks.
- Model quality (not pipeline): this route occasionally returns fluent garbage (even mojibake) with high confidence and `review_required=false` that still passes schema validation — nothing in the pipeline can catch it; eval / LLM-as-judge are the stretch-goal answers in `5-support-intelligence-api.md`.
- `tiktoken.encoding_for_model()` falls back to `o200k_base` on `KeyError`; prompt estimates add `CHAT_OVERHEAD_TOKENS=60`.
- Per-request tracing via `X-Request-ID` middleware + `request_id` in log lines (`app/logging_config.py`); `analyze_ticket` logs `ticket_id latency_ms prompt_tokens completion_tokens estimated_cost_usd success`. `curl -i` exposes the request id for `logs api | grep <id>`.
- `PRICING` snapshot is dated 2026-09-21 in-code — re-verify before treating costs as authoritative. No auth, rate limiting, or caching (stretch goals in `5-support-intelligence-api.md`).
