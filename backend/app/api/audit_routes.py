"""
Audit log API endpoints.

Provides read-only access to the persistent audit trail stored in SQLite.
Authentication is enforced by the global auth middleware in main.py for all
/api/* paths not in the public_paths whitelist.

Routes:
    GET /api/audit/events  -- paginated list of audit events with optional filters
    GET /api/audit/stats   -- aggregate statistics for the audit dashboard
"""

from typing import Optional

from app.core.audit import get_audit_events, get_audit_stats
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/events")
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    action: Optional[str] = Query(default=None, description="Filter by action prefix (e.g. 'auth_')"),
    user: Optional[str] = Query(default=None, description="Filter by exact username"),
    since: Optional[str] = Query(default=None, description="ISO 8601 lower bound timestamp"),
    until: Optional[str] = Query(default=None, description="ISO 8601 upper bound timestamp"),
):
    """
    Return a paginated list of audit events with optional filters.

    Supports filtering by action prefix, username, and time range.
    Results are ordered by timestamp descending (most recent first).
    """
    return get_audit_events(
        limit=limit,
        offset=offset,
        action_filter=action,
        user_filter=user,
        since=since,
        until=until,
    )


@router.get("/stats")
async def audit_stats():
    """
    Return aggregate statistics for the audit log dashboard:
    total events, top actions, top users, and recent failures.
    """
    return get_audit_stats()
