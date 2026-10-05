from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.repository import get_analytics_summary


router = APIRouter()


@router.get("/analytics/summary")
def get_summary(
    since: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, float | int]:
    """Return aggregated analytics, optionally since ISO datetime."""
    parsed_since: datetime | None = None

    if since is not None:
        try:
            parsed_since = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"{since!r} is not a valid ISO date string.",
            )

    return get_analytics_summary(
        db=db,
        since=parsed_since,
    )
