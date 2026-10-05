import contextvars
import logging


request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """Inject request_id from context var into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id attribute to record."""
        record.request_id = request_id_ctx.get()  # type: ignore[attr-defined]
        return True


formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | "
    "%(request_id)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)
handler.addFilter(RequestIdFilter())

logger = logging.getLogger("support_intelligence_api")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False
