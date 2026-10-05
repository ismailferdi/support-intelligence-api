from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.exceptions import LLMCallError
from app.logging_config import logger, request_id_ctx
from app.routers import analytics, tickets


app = FastAPI(title="support-intelligence-api")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate and propagate X-Request-ID for tracing."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Set request_id ctx, add header to response."""
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


app.add_middleware(RequestIdMiddleware)

app.include_router(analytics.router)
app.include_router(tickets.router)


@app.exception_handler(ValidationError)
async def pydantic_validationerror_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Map Pydantic ValidationError to 422."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(LLMCallError)
async def llm_call_error_exception_handler(
    request: Request, exc: LLMCallError
) -> JSONResponse:
    """Map LLMCallError to 502."""
    return JSONResponse(
        status_code=502,
        content={
            "detail": (
                "the analysis is unavailable and review_required "
                "should be treated as true"
            )
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all 500, log traceback without leaking stack."""
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unexpected error occurred. Please try again later."
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}
