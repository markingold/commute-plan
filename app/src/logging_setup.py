"""
Shared structured logging setup for commute-plan.

Standard fields:
- ts
- level
- msg
- project / project_id
- component
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


_PROJECT = "commute-plan"


def _resolve_level() -> int:
    raw = (os.getenv("LOG_LEVEL") or "WARNING").upper().strip()
    return getattr(logging, raw, logging.INFO)


def configure_logging() -> None:
    """Configure structlog + stdlib logging once per process."""
    if getattr(configure_logging, "_configured", False):
        return

    level = _resolve_level()
    json_logs = (os.getenv("LOG_FORMAT") or "json").lower().strip() != "console"

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.stdlib.add_log_level,
        structlog.processors.EventRenamer("msg"),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    configure_logging._configured = True  # type: ignore[attr-defined]


def get_logger(component: str):
    """Return a logger bound with required project/component fields."""
    configure_logging()
    return structlog.get_logger().bind(
        project=_PROJECT,
        project_id=_PROJECT,
        component=component,
    )
