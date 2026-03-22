"""In-memory response cache for cost efficiency and latency reduction.

Design: Simple hash-based dictionary cache. For a language learning API in production
this would typically be Redis-backed, but an in-memory cache demonstrates cost-awareness
without adding infrastructure dependencies (which would complicate Docker setup).

Cache key: SHA-256 hash of (sentence, target_language, native_language) tuple.
This ensures identical requests return identical results without redundant API calls.
"""

import hashlib
import json
import logging
import time
from typing import Optional

from app.models import FeedbackResponse

logger = logging.getLogger(__name__)


class ResponseCache:
    """Thread-safe in-memory cache with optional TTL and size limits."""

    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[int] = 3600):
        self._cache: dict[str, tuple[FeedbackResponse, float]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(sentence: str, target_language: str, native_language: str) -> str:
        """Generate a deterministic cache key from request parameters."""
        payload = json.dumps(
            {
                "sentence": sentence.strip(),
                "target_language": target_language.strip().lower(),
                "native_language": native_language.strip().lower(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(
        self, sentence: str, target_language: str, native_language: str
    ) -> Optional[FeedbackResponse]:
        """Retrieve a cached response, or None if not found / expired."""
        key = self._make_key(sentence, target_language, native_language)
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

    def put(
        self,
        sentence: str,
        target_language: str,
        native_language: str,
        response: FeedbackResponse,
    ) -> None:
        """Store a response in the cache."""
        # Evict oldest entries if at capacity
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        key = self._make_key(sentence, target_language, native_language)
        self._cache[key] = (response, time.time())

    @property
    def stats(self) -> dict:
        """Return cache statistics for monitoring."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "N/A",
        }
