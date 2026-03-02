"""
Audit logging utilities for the Pseudonymization Tool.

Provides centralized functions for:
- Sensitive data scrubbing in logs (passwords, secrets, paths, UUIDs)
- Structured audit event logging with user context

Used across all API routes to ensure consistent security practices.
"""

import logging
import re
from typing import Any, Optional

from fastapi import Request

logger = logging.getLogger(__name__)


def scrub_sensitive(value: Any) -> Any:
    """
    Remove sensitive data from log output.
    
    Scrubbing rules:
    - Dictionary keys containing "password", "passphrase", "secret", "token", "api_key", "bind_password" are removed
    - File paths like /home/username/ or /tmp/dirname/ are anonymized to /home/*** or /tmp/***
    - UUIDs are truncated to first 8 chars (e.g., abc12345-6789-... → abc12345-****)
    
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
            # Skip sensitive keys entirely
            if any(
                token in key_l 
                for token in ("password", "passphrase", "secret", "token", "api_key", "bind_password")
            ):
                continue
            cleaned[key] = scrub_sensitive(item)
        return cleaned
    
    if isinstance(value, list):
        return [scrub_sensitive(item) for item in value]
    
    if isinstance(value, str):
        # Scrub file paths (e.g., /home/admin/... → /home/***)
        value = re.sub(r'/home/[^/\s]+', '/home/***', value)
        value = re.sub(r'/tmp/[^/\s]+', '/tmp/***', value)
        
        # Scrub full UUIDs (keep first 8 chars for debugging: xxxx-xxxx-... → xxxx-****)
        value = re.sub(
            r'\b([a-f0-9]{8})-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b',
            r'\1-****',
            value
        )
    
    return value


def audit_event(request: Optional[Request], action: str, **details: Any) -> None:
    """
    Log an audit event with user context and scrubbed details.
    
    Extracts user and IP from request context, scrubs sensitive data from details,
    and logs in structured format for audit trail analysis.
    
    Args:
        request: FastAPI Request object (or None for non-HTTP contexts)
        action: Action identifier (e.g., "batch_create", "auth_login", "settings_update")
        **details: Additional context to log (will be scrubbed)
        
    Examples:
        >>> audit_event(request, "batch_create", batch_id="abc-123", files_count=5)
        # Logs: AUDIT action=batch_create user=admin ip=192.168.1.1 details={'batch_id': 'abc-123', ...}
        
        >>> audit_event(None, "system_startup", version="4.1.0")
        # Logs: AUDIT action=system_startup user=anonymous ip=unknown details={'version': '4.1.0'}
    """
    user = "anonymous"
    ip = "unknown"
    
    if request is not None:
        user = getattr(request.state, "auth_user", "anonymous")
        ip = request.client.host if request.client else "unknown"
    
    cleaned = scrub_sensitive(details)
    logger.info("AUDIT action=%s user=%s ip=%s details=%s", action, user, ip, cleaned)
