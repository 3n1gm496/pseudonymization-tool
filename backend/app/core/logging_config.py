"""
Structured logging configuration for the application.
Provides JSON-formatted logs with correlation IDs and request context.
"""

import logging
import sys
from typing import Any

import structlog
from app import __version__
from structlog.typing import EventDict, Processor


def add_app_context(logger: logging.Logger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log entries."""
    event_dict["app"] = "pseudonymization-tool"
    event_dict["version"] = __version__
    return event_dict


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: If True, output logs in JSON format
    """
    # Configure structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_app_context,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console output for development
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Adjust third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)


def log_request_start(method: str, path: str, request_id: str, **kwargs: Any) -> None:
    """Log the start of a request."""
    logger = get_logger("app.request")
    logger.info("request_started", method=method, path=path, request_id=request_id, **kwargs)


def log_request_end(
    method: str, path: str, request_id: str, status_code: int, duration_ms: float, **kwargs: Any
) -> None:
    """Log the end of a request."""
    logger = get_logger("app.request")
    logger.info(
        "request_completed",
        method=method,
        path=path,
        request_id=request_id,
        status_code=status_code,
        duration_ms=round(duration_ms, 2),
        **kwargs,
    )


def log_error(error_type: str, error_message: str, **kwargs: Any) -> None:
    """Log an error with context."""
    logger = get_logger("app.error")
    logger.error("error_occurred", error_type=error_type, error_message=error_message, **kwargs)
