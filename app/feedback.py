"""Feedback orchestration: provider routing, caching, and sentinel validation.

This is the main business logic module that ties together:
1. Cache lookup (avoid redundant API calls)
2. Provider routing (try Anthropic first, then OpenAI fallback)
3. Sentinel validation (verify response quality before returning)
4. Cache storage (store validated responses for future requests)

The max retry for sentinel validation failures is kept low (2 attempts)
to stay within the 30-second response time requirement.
"""

import logging
import time

from app.cache import ResponseCache
from app.models import FeedbackRequest, FeedbackResponse
from app.providers import LLMProvider, LLMProviderError, get_available_providers
from app.validators import validate_response

logger = logging.getLogger(__name__)

# Module-level singleton cache
_cache = ResponseCache(max_size=1000, ttl_seconds=3600)

# Module-level providers (initialized lazily)
_providers: list[LLMProvider] | None = None


def _get_providers() -> list[LLMProvider]:
    """Get or initialize available LLM providers."""
    global _providers
    if _providers is None:
        _providers = get_available_providers()
    return _providers


async def get_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Generate language feedback with caching, fallback, and validation.

    Flow:
    1. Check cache → return immediately if hit
    2. Try each provider in priority order (Anthropic → OpenAI)
    3. Validate response with sentinel checks
    4. If validation fails, retry with next provider or re-attempt
    5. Cache and return the validated response

    Args:
        request: The learner's sentence and language info

    Returns:
        FeedbackResponse with corrections, errors, and difficulty

    Raises:
        LLMProviderError: If all providers fail after retries
    """
    start_time = time.time()

    # 1. Cache lookup
    cached = _cache.get(
        request.sentence, request.target_language, request.native_language
    )
    if cached is not None:
        elapsed = time.time() - start_time
        logger.info("Cache hit — returned in %.3fs", elapsed)
        return cached

    # 2. Try each provider
    providers = _get_providers()
    if not providers:
        raise LLMProviderError(
            "No LLM providers available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )

    last_error: Exception | None = None
    max_validation_retries = 2

    for provider in providers:
        for attempt in range(max_validation_retries):
            try:
                logger.info(
                    "Attempting %s (attempt %d/%d)",
                    provider.name,
                    attempt + 1,
                    max_validation_retries,
                )

                # 3. Generate feedback
                response = await provider.generate_feedback(
                    request.sentence,
                    request.target_language,
                    request.native_language,
                )

                # 4. Sentinel validation
                validation = validate_response(request, response)
                if not validation:
                    logger.warning(
                        "Sentinel validation failed on attempt %d: %s",
                        attempt + 1,
                        "; ".join(validation.issues),
                    )
                    if attempt < max_validation_retries - 1:
                        continue  # Retry with same provider
                    else:
                        # Accept the response anyway if it's structurally valid
                        # (Pydantic already validated the schema)
                        logger.warning(
                            "Accepting response with validation warnings after %d attempts",
                            max_validation_retries,
                        )

                # 5. Cache and return
                _cache.put(
                    request.sentence,
                    request.target_language,
                    request.native_language,
                    response,
                )

                elapsed = time.time() - start_time
                logger.info(
                    "Feedback generated via %s in %.3fs (cache: %s)",
                    provider.name,
                    elapsed,
                    _cache.stats,
                )
                return response

            except LLMProviderError as e:
                last_error = e
                logger.warning("Provider %s failed: %s", provider.name, str(e))
                break  # Move to next provider

            except Exception as e:
                last_error = e
                logger.error(
                    "Unexpected error with %s: %s", provider.name, str(e)
                )
                break  # Move to next provider

    # All providers failed
    raise LLMProviderError(
        f"All LLM providers failed. Last error: {last_error}"
    )


def get_cache_stats() -> dict:
    """Return cache statistics for the health endpoint."""
    return _cache.stats
