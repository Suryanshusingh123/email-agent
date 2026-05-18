"""
history.py — Endpoints for querying persisted email summaries.

These endpoints read from the database — they work even after a server restart,
unlike the in-memory polling results which are lost on restart.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.db_service import get_email_history, get_email_stats, record_to_dict

router = APIRouter()


@router.get("/")
def email_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    priority: str = Query(default=None, description="Filter: high, medium, low"),
    category: str = Query(default=None, description="Filter: work, security, newsletter, etc."),
    action_required: bool = Query(default=None, description="Filter by action required"),
    db: Session = Depends(get_db),
):
    """
    Return paginated email history from the database.

    WHY Depends(get_db)?
      This is FastAPI's dependency injection. When the endpoint is called,
      FastAPI calls get_db(), passes the session in, and closes it when done.
      You never manage the session lifecycle manually in the endpoint.
      This is the correct FastAPI pattern — always use it for DB sessions.
    """
    records, total = get_email_history(
        db=db,
        limit=limit,
        offset=offset,
        priority=priority,
        category=category,
        action_required=action_required,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "emails": [record_to_dict(r) for r in records],
    }


@router.get("/stats")
def email_stats(db: Session = Depends(get_db)):
    """
    Return aggregate statistics across all persisted emails.
    Use this to power a dashboard.
    """
    return get_email_stats(db)
