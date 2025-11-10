"""
Module: logger.py
Description: Structured logging configuration for the Triggers API.

Configures structlog for JSON output optimized for CloudWatch Logs.
Provides consistent logging across all modules with proper context
and structured data.

Key Components:
- JSON output for CloudWatch compatibility
- Timestamp and log level processors
- Context binding helpers
- get_logger() helper function

Dependencies: structlog, datetime
Author: Triggers API Team
"""

import structlog
from datetime import datetime, timezone


def _add_timestamp(logger, method_name, event_dict):
    """
    Add ISO 8601 timestamp to log entries.

    Args:
        logger: Logger instance
        method_name: Log method name (info, error, etc.)
        event_dict: Current log event dictionary

    Returns:
        Updated event dictionary with timestamp
    """
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat() + "Z"
    return event_dict


def _add_log_level(logger, method_name, event_dict):
    """
    Add log level to event dictionary.

    Args:
        logger: Logger instance
        method_name: Log method name (info, error, etc.)
        event_dict: Current log event dictionary

    Returns:
        Updated event dictionary with level
    """
    event_dict["level"] = method_name.upper()
    return event_dict


# Configure structlog for JSON output optimized for CloudWatch
structlog.configure(
    processors=[
        # Add timestamp and log level
        _add_timestamp,
        _add_log_level,
        # Add exception information
        structlog.processors.format_exc_info,
        # Render as JSON for CloudWatch compatibility
        structlog.processors.JSONRenderer(),
    ],
    # Use standard library logger factory for compatibility
    logger_factory=structlog.WriteLoggerFactory(),
    # Enable context binding
    wrapper_class=structlog.BoundLogger,
    # Cache logger on first use for performance
    cache_logger_on_first_use=True,
)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a configured structlog logger instance.

    Creates a logger with the specified name that outputs JSON
    formatted logs suitable for CloudWatch Logs ingestion.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Event created", event_id="evt_123", status="pending")
        {"event": "Event created", "event_id": "evt_123", "status": "pending", "timestamp": "2024-01-15T10:30:00Z", "level": "INFO"}
    """
    return structlog.get_logger(name)
