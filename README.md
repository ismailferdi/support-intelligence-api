# Support Intelligence API

## Overview

An AI capability exposed as a usable application service — **not a chatbot**. Clients `POST` a raw customer-support ticket and get back a structured, schema-validated analysis (category, priority, sentiment, summary, suggested response, confidence, review flag) plus per-request metadata: token usage, estimated USD cost, latency, and the model used. Every request is persisted to Postgres, and an analytics endpoint aggregates spend, latency, and failure rate over time.

## Architecture

```
Client
  │
  ▼
REST API  (app/routers/tickets.py, app/main.py — thin layer, no business logic)
  │
  ▼
Persist raw ticket  (app/repository.py: save_ticket → tickets table)
  │
  ▼
Prompt construction  (app/prompts.py + app/tokens.py — truncate to MAX_INPUT_TOKENS,
                      system prompt with JSON schema + few-shot examples)
  │
  ▼
LLM API  (app/llm_client.py — OpenAI SDK via OpenRouter, tenacity retries
          on timeout/connection only, reasoning suppressed via extra_body)
  │
  ▼
Structured validation  (app/validation.py — validate against TicketAnalysis schema,
                        exactly one retry with correction text, else safe fallback)
  │
  ▼
Database  (app/repository.py: save_analysis → analyses table with tokens/cost/latency)
  │
  ▼
Analytics  (GET /analytics/summary aggregates count, latency, cost, failure rate)
```

All orchestration lives in one place: `analyze_ticket()` in `app/analysis_service.py`.

## Roadmap Topic Mapping

| Roadmap topic | Repo component |
|---|---|
| LLM inference, using pre-trained models | `app/llm_client.py` — Chat Completions call wrapper |
| OpenAI API / Chat Completions API | `app/llm_client.py` (OpenAI SDK pointed at OpenRouter) |
| Managing tokens / maximum tokens / token counting | `app/tokens.py` — `count_tokens`, `truncate_to_token_limit` |
| Pricing considerations | `app/llm_client.py` (`PRICING` + `calculate_cost`) and `/analytics/summary` surfacing spend |
| Structured output | `app/validation.py` — `parse_and_validate` / `parse_with_retry` |
| Prompt design | `app/prompts.py` — system prompt with schema + 3 few-shot examples |
| Context-window management | `app/tokens.py` truncation wired into `analyze_ticket()` via `MAX_INPUT_TOKENS` |
| Cost/latency trade-offs | `app/llm_client.py`, `/analytics/summary`, and the model-routing stretch goal |
| AI application development (not notebook experimentation) | The whole service: config, API, DB, tests, Docker, CI |

## Local setup

Prerequisites: Python ≥3.12, [`uv`](https://docs.astral.sh/uv/), Docker (for Postgres), an OpenRouter/OpenAI API key.

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment (required — app fails at import without these)
cp .env.example .env
# then edit .env: set OPENAI_API_KEY, POSTGRES_USER/PASSWORD/DB.
# NOTE: .env.example has two traps — OPENAI_APY_KEY is a typo (use OPENAI_API_KEY),
# and OPENAI_MODEL=openai/gpt-oss-20b matches no PRICING key (use bare gpt-oss-20b).

# 3. Start dev Postgres
docker compose -f docker/docker-compose.dev.yml up -d

# 4. Create tables (override DATABASE_URL to point at localhost if needed)
uv run python -m scripts.create_tables

# 5. Run the API
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API, or `GET /health` → `{"status":"ok"}`.

## Docker setup (full stack)

```bash
# Build and start API + Postgres (run from repo root)
docker compose --env-file .env -f docker/docker-compose.yml up --build -d

# Create tables inside the stack
docker compose --env-file .env -f docker/docker-compose.yml exec api python -m scripts.create_tables

# Verify end to end
curl localhost:8000/health
curl -X POST localhost:8000/tickets -H 'Content-Type: application/json' \
  -d '{"text":"I was charged twice this month, please refund the duplicate"}'
```

Notes:

- `--env-file .env` is required: with `-f docker/...`, Compose looks for `.env` next to the compose file and ignores the repo-root one otherwise.
- Postgres has a healthcheck and the API waits for `service_healthy`, so no manual ordering is needed.
- Model note: the client sends `reasoning: {effort: low, exclude: true}` because `gpt-oss-20b` via OpenRouter otherwise spends its budget in the reasoning channel and returns empty `content` (every request then degrades to the fallback). Keep it.
- The API runs from the image, not your working tree — after code edits, rebuild with `--force-recreate api`. Both compose files share one Postgres volume: don't `down -v` unless you mean to wipe the dev database too.

## API reference

### `POST /tickets` → `201`

```json
// request
{"text": "I was charged twice this month, please refund the duplicate"}
```

```json
// response (201)
{
  "analysis": {
    "category": "billing",
    "priority": "high",
    "sentiment": "negative",
    "summary": "Customer reports being charged twice this month.",
    "suggested_response": "Sorry about the double charge. We're checking your billing history and will refund the duplicate payment.",
    "confidence": 0.95,
    "review_required": false
  },
  "ticket_id": "4b5bc145-40f1-467e-bb5f-ac8145ce7df7",
  "model_used": "gpt-oss-20b",
  "prompt_tokens": 740,
  "completion_tokens": 97,
  "total_tokens": 837,
  "estimated_cost_usd": 0.00004415,
  "latency_ms": 3128,
  "created_at": "2026-10-05T08:30:43.273338Z"
}
```

`text` must be 1–5000 chars, else `422`. If the LLM call or validation fails, you still get `201` with a safe placeholder (`category: other`, `confidence: 0.0`, `review_required: true`, zero tokens) instead of a `500`.

### `GET /tickets/{ticket_id}` → `200` or `404`

Returns the same shape as above. Both a malformed UUID and an unknown id return `404`.

### `GET /analytics/summary?since=<ISO datetime>` → `200`

```json
{"total_requests": 4, "avg_latency_ms": 5427.75, "total_cost_usd": 0.00012788, "failure_rate": 0.25}
```

`since` is optional (filters to records created at/after it). An unparseable `since` returns `404` (not `422`).

## Cost and token tracking

Stored per request in the `analyses` table: `model_used`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd` (`Numeric(12,8)`), `latency_ms`, plus `success` and `error_message`. Cost comes from a hardcoded `PRICING` table in `app/llm_client.py` (USD per 1k input/output tokens, snapshot dated 2026-09-21 — re-verify before treating figures as authoritative; the model string must match a `PRICING` key exactly or cost calculation raises `KeyError`).

`GET /analytics/summary` aggregates over all (or `since`-filtered) records:

- `total_requests` — number of analyses stored
- `avg_latency_ms` — mean end-to-end latency
- `total_cost_usd` — summed estimated spend
- `failure_rate` — fraction recorded with `success=False` (LLM failures degrade to the review-required placeholder, so this is the number to watch)

## Running tests

```bash
uv run pytest tests/test_tokens.py -v   # single file
uv run pytest tests/ -v                 # full suite (33 tests)
uv run pytest tests/ -v --cov=app --cov-report=term-missing   # with coverage (as in CI)
uv run flake8 app/ tests/               # lint (no config file; must stay clean)
```

No Postgres or API key needed: `tests/conftest.py` uses in-memory SQLite (per-test rollback) and overrides `get_db`; the LLM is always mocked (`fake_openai_response` factory; mock `parse_with_retry` for API/service tests, `_create_completion` for retry tests). CI (`.github/workflows/ci.yml`) runs tests with dummy env vars (required because `Settings()` validates at import), then flake8, then a `docker build`.

## Known simplifications

- Few-shot examples in the system prompt are hand-written, not curated from real historical tickets.
- The `PRICING` table is a manually-updated snapshot (2026-09-21), not a live price feed.
- No authentication, rate limiting, or response caching on the API.
- Tests run against SQLite while production runs Postgres (Postgres-specific behavior isn't covered).
- Model output quality varies by provider route: fluent-but-wrong analyses occasionally pass schema validation with high confidence and `review_required: false`. Catching those needs the eval / LLM-as-judge stretch goals, not more pipeline code.
