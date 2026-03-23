"""Structured JSON logging with correlation ID support.

Design decisions:
- Custom JSON formatter (no structlog dependency) — shows understanding of Python
  logging internals and keeps requirements.txt minimal.
- contextvars for correlation ID — async-safe, works with FastAPI's async handlers.
- Request/response logging middleware — captures latency, status, path for each request.
- Environment-configurable format — JSON for production, human-readable for development.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable for request correlation ID (async-safe)
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "text"


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines for structured logging.

    Output fields: timestamp, level, message, logger, correlation_id,
    plus any extra fields attached to the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": correlation_id_var.get("-"),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields
        for key in ("path", "method", "status_code", "latency_ms",
                     "client_ip", "provider", "tokens_in", "tokens_out"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def setup_logging() -> None:
    """Configure application logging based on LOG_FORMAT environment variable.

    - LOG_FORMAT=json (default): Structured JSON lines for production
    - LOG_FORMAT=text: Human-readable format for development
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler()

    if LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        ))

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs each request with correlation ID and latency.

    Sets a correlation ID for each request (from X-Request-ID header or
    auto-generated UUID). Logs request start and response completion with
    latency metrics.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract correlation ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        correlation_id_var.set(request_id)

        start_time = time.time()
        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        ).split(",")[0].strip()

        logger = logging.getLogger("api")

        # Skip logging for health checks (noisy)
        is_health = request.url.path == "/health"

        if not is_health:
            logger.info(
                "→ %s %s",
                request.method,
                request.url.path,
                extra={"path": request.url.path, "method": request.method,
                       "client_ip": client_ip},
            )

        response = await call_next(request)

        latency_ms = round((time.time() - start_time) * 1000, 2)

        if not is_health:
            logger.info(
                "← %s %s %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                latency_ms,
                extra={"path": request.url.path, "method": request.method,
                       "status_code": response.status_code,
                       "latency_ms": latency_ms, "client_ip": client_ip},
            )

        # Add correlation ID to response headers
        response.headers["X-Request-ID"] = request_id
        return response
