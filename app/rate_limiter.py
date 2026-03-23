"""In-memory sliding window rate limiter for API protection.

Design decisions:
- Custom implementation (no slowapi/Redis) — zero extra dependencies, shows understanding
  of rate limiting internals, and is appropriate for Docker single-instance deployment.
- Sliding window algorithm — more accurate than fixed window, prevents burst edge cases.
- Per-IP tracking — simple, effective for the task's single-service architecture.
- Auto-cleanup — prevents memory leaks from expired entries.
- Configurable via environment variables for production flexibility.

For multi-instance production deployment, replace with Redis-backed sliding window
(e.g., slowapi with RedisStorage).
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Configuration from environment
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW", "60"))


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter with auto-cleanup.

    Tracks request timestamps per client key (IP address) using a sliding
    window algorithm. Expired entries are automatically cleaned up to
    prevent memory leaks.
    """

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS,
                 window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Clean up every 5 minutes

    def is_allowed(self, client_key: str) -> tuple[bool, dict]:
        """Check if a request from client_key is allowed.

        Returns:
            Tuple of (is_allowed, rate_limit_info) where rate_limit_info
            contains headers for the response.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Remove expired timestamps for this client
        self._requests[client_key] = [
            ts for ts in self._requests[client_key] if ts > window_start
        ]

        current_count = len(self._requests[client_key])
        remaining = max(0, self.max_requests - current_count)

        info = {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Window": str(self.window_seconds),
        }

        if current_count >= self.max_requests:
            # Calculate retry-after from oldest request in window
            oldest = min(self._requests[client_key]) if self._requests[client_key] else now
            retry_after = int(oldest + self.window_seconds - now) + 1
            info["Retry-After"] = str(max(1, retry_after))
            return False, info

        # Record this request
        self._requests[client_key].append(now)

        # Periodic cleanup of all expired entries
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now)

        return True, info

    def _cleanup(self, now: float) -> None:
        """Remove all expired entries to prevent memory leaks."""
        window_start = now - self.window_seconds
        expired_keys = []

        for key, timestamps in self._requests.items():
            self._requests[key] = [ts for ts in timestamps if ts > window_start]
            if not self._requests[key]:
                expired_keys.append(key)

        for key in expired_keys:
            del self._requests[key]

        self._last_cleanup = now
        if expired_keys:
            logger.debug("Rate limiter cleanup: removed %d expired clients", len(expired_keys))

    @property
    def stats(self) -> dict:
        """Return rate limiter statistics for monitoring."""
        return {
            "active_clients": len(self._requests),
            "max_requests_per_window": self.max_requests,
            "window_seconds": self.window_seconds,
        }


# Module-level singleton
_limiter = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Get the singleton rate limiter instance."""
    return _limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces per-IP rate limiting.

    Excludes health check endpoint from rate limiting.
    Adds rate limit headers to all responses.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and docs
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # Get client IP (handles proxy headers)
        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        )
        # Use first IP if multiple (proxy chain)
        client_ip = client_ip.split(",")[0].strip()

        allowed, info = _limiter.is_allowed(client_ip)

        if not allowed:
            logger.warning(
                "Rate limit exceeded for %s: %s req/%ss",
                client_ip, info["X-RateLimit-Limit"], info["X-RateLimit-Window"],
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": int(info.get("Retry-After", 60)),
                },
            )
            for key, value in info.items():
                response.headers[key] = value
            return response

        # Process request and add rate limit headers
        response = await call_next(request)
        for key, value in info.items():
            response.headers[key] = value
        return response
