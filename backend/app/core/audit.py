"""
Audit logging utilities for the Pseudonymization Tool.

Provides centralized functions for:
- Sensitive data scrubbing in logs (passwords, secrets, paths, UUIDs)
- Structured audit event logging with user context
- Persistent audit trail stored in SQLite (PSEUDONYMIZER_STATE_DIR/audit.db)
- Query API for the audit log viewer in the UI

The audit log is stored in a SQLite database on the persistent state volume
so that it survives container restarts. The database is created automatically
on first use.

Thread-safety: SQLite connections are opened per-call with WAL mode enabled,
which allows concurrent readers and a single writer without blocking.
"""

import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite database path
# ---------------------------------------------------------------------------

_DB_LOCK = threading.Lock()
_DB_INITIALIZED = False


def _get_db_path() -> str:
    """Return the path to the audit SQLite database."""
    state_dir = os.environ.get("PSEUDONYMIZER_STATE_DIR", "/app/state")
    return os.path.join(state_dir, "audit.db")


def _get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and row_factory."""
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema() -> None:
    """Create the audit_events table if it does not exist (idempotent)."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with _DB_LOCK:
        if _DB_INITIALIZED:
            return
        try:
            conn = _get_connection()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    action      TEXT    NOT NULL,
                    user        TEXT    NOT NULL DEFAULT 'anonymous',
                    ip          TEXT    NOT NULL DEFAULT 'unknown',
                    details     TEXT    NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user)")
            conn.commit()
            conn.close()
            _DB_INITIALIZED = True
            logger.info("audit: SQLite database initialized at %s", _get_db_path())
        except Exception as exc:  # pragma: no cover
            logger.error("audit: failed to initialize SQLite database: %s", exc)


# ---------------------------------------------------------------------------
# Sensitive data scrubbing
# ---------------------------------------------------------------------------


def scrub_sensitive(value: Any) -> Any:
    """
    Remove sensitive data from log output.

    Scrubbing rules:
    - Dictionary keys containing "password", "passphrase", "secret", "token",
      "api_key", "bind_password" are removed
    - File paths like /home/username/ or /tmp/dirname/ are anonymized
    - UUIDs are truncated to first 8 chars (e.g., abc12345-6789-... -> abc12345-****)

    Args:
        value: Any value (dict, list, str, or other type)

    Returns:
        Scrubbed value with sensitive data removed/anonymized

    Examples:
        >>> scrub_sensitive({"password": "secret123", "username": "admin"})
        {"username": "admin"}
        >>> scrub_sensitive("/home/alice/file.txt")
        "/home/***/file.txt"
        >>> scrub_sensitive("batch-abc12345-6789-4bcd-8e90-123456789abc")
        "batch-abc12345-****"
    """
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if any(
                token in key_l
                for token in (
                    "password",
                    "passphrase",
                    "secret",
                    "token",
                    "api_key",
                    "bind_password",
                )
            ):
                continue
            cleaned[key] = scrub_sensitive(item)
        return cleaned
    if isinstance(value, list):
        return [scrub_sensitive(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"/home/[^/\s]+", "/home/***", value)
        value = re.sub(
            r"/tmp/[^/\s]+", "/tmp/***", value
        )  # nosec B108 -- regex per sanitizzare path nei log, non uso reale di /tmp
        value = re.sub(
            r"\b([a-f0-9]{8})-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b",
            r"\1-****",
            value,
        )
    return value


# ---------------------------------------------------------------------------
# Core audit function
# ---------------------------------------------------------------------------


def audit_event(request: Optional[Request], action: str, **details: Any) -> None:
    """
    Log an audit event with user context and scrubbed details.

    Writes to both the Python logger (for log aggregators like ELK/Loki) and
    to the persistent SQLite database (for the UI audit log viewer).

    Args:
        request: FastAPI Request object (or None for non-HTTP contexts)
        action: Action identifier (e.g., "batch_create", "auth_login", "settings_update")
        **details: Additional context to log (will be scrubbed)

    Examples:
        >>> audit_event(request, "batch_create", batch_id="abc-123", files_count=5)
        # Logs: AUDIT action=batch_create user=admin ip=192.168.1.1 details={...}
        >>> audit_event(None, "system_startup", version="5.0.0")
        # Logs: AUDIT action=system_startup user=anonymous ip=unknown details={...}
    """
    user = "anonymous"
    ip = "unknown"
    if request is not None:
        user = getattr(request.state, "auth_user", "anonymous")
        ip = request.client.host if request.client else "unknown"

    cleaned = scrub_sensitive(details)

    # 1. Log to Python logger (for log aggregators)
    logger.info("AUDIT action=%s user=%s ip=%s details=%s", action, user, ip, cleaned)

    # 2. Persist to SQLite
    _ensure_schema()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO audit_events (timestamp, action, user, ip, details) VALUES (?, ?, ?, ?, ?)",
            (timestamp, action, user, ip, json.dumps(cleaned)),
        )
        conn.commit()
        conn.close()
    except Exception as exc:  # pragma: no cover
        logger.error("audit: failed to persist audit event to SQLite: %s", exc)


# ---------------------------------------------------------------------------
# Query API (used by /api/audit/events endpoint)
# ---------------------------------------------------------------------------


def get_audit_events(
    limit: int = 100,
    offset: int = 0,
    action_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query audit events from the SQLite database with optional filters.

    Args:
        limit: Maximum number of events to return (default 100, max 500)
        offset: Pagination offset
        action_filter: Filter by action prefix (e.g., "auth_" matches all auth events)
        user_filter: Filter by exact username
        since: ISO 8601 timestamp -- return events after this time
        until: ISO 8601 timestamp -- return events before this time

    Returns:
        Dict with keys: events (list), total (int), limit (int), offset (int)
    """
    _ensure_schema()
    limit = min(max(1, limit), 500)

    conditions: List[str] = []
    params: List[Any] = []

    if action_filter:
        conditions.append("action LIKE ?")
        params.append(action_filter.rstrip("%") + "%")
    if user_filter:
        conditions.append("user = ?")
        params.append(user_filter)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if until:
        conditions.append("timestamp <= ?")
        params.append(until)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    try:
        conn = _get_connection()

        total_row = conn.execute(
            f"SELECT COUNT(*) FROM audit_events {where_clause}",  # nosec B608
            params,
        ).fetchone()
        total = total_row[0] if total_row else 0

        rows = conn.execute(
            f"SELECT id, timestamp, action, user, ip, details "  # nosec B608
            f"FROM audit_events {where_clause} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        conn.close()

        events = []
        for row in rows:
            try:
                details = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                details = {}
            events.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "action": row["action"],
                    "user": row["user"],
                    "ip": row["ip"],
                    "details": details,
                }
            )

        return {"events": events, "total": total, "limit": limit, "offset": offset}

    except Exception as exc:  # pragma: no cover
        logger.error("audit: failed to query audit events: %s", exc)
        return {"events": [], "total": 0, "limit": limit, "offset": offset}


def get_audit_stats() -> Dict[str, Any]:
    """
    Return aggregate statistics for the audit log dashboard.

    Returns:
        Dict with: total_events, events_by_action (top 10), events_by_user,
        recent_failures (last 10 failed auth events)
    """
    _ensure_schema()
    try:
        conn = _get_connection()

        total = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

        by_action = conn.execute(
            "SELECT action, COUNT(*) as count FROM audit_events " "GROUP BY action ORDER BY count DESC LIMIT 10"
        ).fetchall()

        by_user = conn.execute(
            "SELECT user, COUNT(*) as count FROM audit_events " "GROUP BY user ORDER BY count DESC LIMIT 10"
        ).fetchall()

        recent_failures = conn.execute(
            "SELECT id, timestamp, action, user, ip FROM audit_events "
            "WHERE action LIKE 'auth_%failed%' OR action LIKE '%_error' "
            "ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()

        conn.close()

        return {
            "total_events": total,
            "events_by_action": [{"action": r["action"], "count": r["count"]} for r in by_action],
            "events_by_user": [{"user": r["user"], "count": r["count"]} for r in by_user],
            "recent_failures": [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "action": r["action"],
                    "user": r["user"],
                    "ip": r["ip"],
                }
                for r in recent_failures
            ],
        }
    except Exception as exc:  # pragma: no cover
        logger.error("audit: failed to compute audit stats: %s", exc)
        return {
            "total_events": 0,
            "events_by_action": [],
            "events_by_user": [],
            "recent_failures": [],
        }
