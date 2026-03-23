"""Async-safe in-memory response cache with in-flight request deduplication.

Features:
- asyncio.Lock for concurrent access safety in async context
- SHA-256 cache key with input normalization (.strip().lower())
- TTL-based expiration with configurable max size
- In-flight request deduplication: concurrent identical requests share one
  LLM call via asyncio.Future (prevents redundant API spending)
- Hit/miss statistics for monitoring via /health endpoint

Design: Simple hash-based dictionary cache. For production at scale this would
be Redis-backed, but an in-memory cache demonstrates cost-awareness without
adding infrastructure dependencies (which would complicate Docker setup).
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Optional

from app.models import FeedbackResponse

logger = logging.getLogger(__name__)


class ResponseCache:
    """Async-safe in-memory cache with TTL, size limits, and deduplication."""

    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[int] = 3600):
        self._cache: dict[str, tuple[FeedbackResponse, float]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._dedup_hits = 0
        self._lock = asyncio.Lock()
        # In-flight deduplication: maps cache key → Future for pending requests
        self._in_flight: dict[str, asyncio.Future[FeedbackResponse]] = {}

    @staticmethod
    def _make_key(sentence: str, target_language: str, native_language: str) -> str:
        """Generate a deterministic cache key from request parameters.

        Input normalization ensures case/whitespace differences hit same entry:
        "Yo fui" and " yo fui " → same cache key.
        """
        payload = json.dumps(
            {
                "sentence": sentence.strip(),
                "target_language": target_language.strip().lower(),
                "native_language": native_language.strip().lower(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def get(
        self, sentence: str, target_language: str, native_language: str
    ) -> Optional[FeedbackResponse]:
        """Retrieve a cached response, or None if not found / expired."""
        key = self._make_key(sentence, target_language, native_language)
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            response, timestamp = entry
            if self._ttl_seconds and (time.time() - timestamp) > self._ttl_seconds:
                # Entry expired
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            logger.debug("Cache hit for key %s", key[:12])
            return response

    async def put(
        self,
        sentence: str,
        target_language: str,
        native_language: str,
        response: FeedbackResponse,
    ) -> None:
        """Store a response in the cache."""
        async with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
                logger.debug("Cache eviction: removed oldest entry")

            key = self._make_key(sentence, target_language, native_language)
            self._cache[key] = (response, time.time())

    def get_in_flight(
        self, sentence: str, target_language: str, native_language: str
    ) -> Optional[asyncio.Future[FeedbackResponse]]:
        """Check if an identical request is already being processed.

        Returns the Future if found, or None if no in-flight request.
        """
        key = self._make_key(sentence, target_language, native_language)
        future = self._in_flight.get(key)
        if future is not None:
            self._dedup_hits += 1
            logger.info("In-flight dedup hit for key %s", key[:12])
        return future

    def set_in_flight(
        self, sentence: str, target_language: str, native_language: str
    ) -> asyncio.Future[FeedbackResponse]:
        """Register an in-flight request and return its Future.

        Caller should set the Future's result when the LLM response arrives.
        """
        key = self._make_key(sentence, target_language, native_language)
        loop = asyncio.get_event_loop()
        future: asyncio.Future[FeedbackResponse] = loop.create_future()
        self._in_flight[key] = future
        return future

    def resolve_in_flight(
        self, sentence: str, target_language: str, native_language: str,
        response: FeedbackResponse,
    ) -> None:
        """Resolve an in-flight request, notifying all waiters."""
        key = self._make_key(sentence, target_language, native_language)
        future = self._in_flight.pop(key, None)
        if future is not None and not future.done():
            future.set_result(response)

    def cancel_in_flight(
        self, sentence: str, target_language: str, native_language: str,
        error: Exception,
    ) -> None:
        """Cancel an in-flight request due to error."""
        key = self._make_key(sentence, target_language, native_language)
        future = self._in_flight.pop(key, None)
        if future is not None and not future.done():
            future.set_exception(error)

    @property
    def stats(self) -> dict:
        """Return cache statistics for monitoring."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "N/A",
            "dedup_hits": self._dedup_hits,
        }
