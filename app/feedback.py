from __future__ import annotations

"""Feedback orchestration: provider routing, caching, and sentinel validation.

This is the main business logic module that ties together:
1. Input guardrails (prompt injection detection — warn-only)
2. Cache lookup with async-safe locking (avoid redundant API calls)
2.5. In-flight request deduplication (concurrent identical requests share one LLM call)
3. Explanation language validation (post-processing with langdetect)
4. Provider routing (try OpenAI first, then Anthropic fallback)
5. Sentinel validation (verify response quality before returning)
6. Localized fallback responses (graceful degradation in learner's native language)
7. Cache storage (store validated responses for future requests)
8. Token usage tracking (cost awareness)

The max retry for sentinel validation failures is kept low (2 attempts)
to stay within the 30-second response time requirement.
"""

import logging
import time
import uuid

from app.cache import ResponseCache
from app.fallbacks import build_fallback_response
from app.guardrails import scan_input
from app.language_check import check_explanation_language
from app.metrics import get_metrics_tracker, score_response
from app.models import FeedbackRequest, FeedbackResponse
from app.providers import LLMProvider, LLMProviderError, LLMUsage, get_available_providers
from app.validators import validate_response

logger = logging.getLogger(__name__)

# Module-level singleton cache
_cache = ResponseCache(max_size=1000, ttl_seconds=3600)

# Module-level providers (initialized on first use)
_providers: list[LLMProvider] | None = None

# Cumulative token usage for cost monitoring
_total_usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0}


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
    1.5. Check in-flight dedup → await existing Future if same request in progress
    2. Try each provider in priority order (OpenAI → Anthropic)
    3. Validate response with sentinel checks
    4. If validation fails, retry with next provider or re-attempt
    4.5. Check explanation language, reflexion retry if mismatch
    5. Cache and return the validated response
    6. On total failure → return localized fallback response

    Args:
        request: The learner's sentence and language info

    Returns:
        FeedbackResponse with corrections, errors, and difficulty

    Raises:
        LLMProviderError: If all providers fail and fallback is disabled
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # 0. Input guardrails (warn-only — logs but never blocks)
    guardrail_result = scan_input(request.sentence)
    if not guardrail_result.is_safe:
        logger.warning(
            "[%s] Guardrail alert: risk_score=%.1f categories=%s",
            request_id,
            guardrail_result.risk_score,
            [v[0] for v in guardrail_result.violations],
        )

    # 1. Cache lookup (async-safe)
    cached = await _cache.get(
        request.sentence, request.target_language, request.native_language
    )
    if cached is not None:
        elapsed = time.time() - start_time
        logger.info("[%s] Cache hit — returned in %.3fs", request_id, elapsed)
        return cached

    # 1.5. In-flight request deduplication
    # If an identical request is already being processed, wait for it
    in_flight_future = _cache.get_in_flight(
        request.sentence, request.target_language, request.native_language
    )
    if in_flight_future is not None:
        logger.info("[%s] Dedup: awaiting in-flight request", request_id)
        try:
            return await in_flight_future
        except Exception:
            # If the in-flight request failed, we'll try ourselves
            logger.info("[%s] In-flight request failed, retrying", request_id)

    # Register ourselves as the in-flight handler for this request
    future = _cache.set_in_flight(
        request.sentence, request.target_language, request.native_language
    )

    # 2. Try each provider
    providers = _get_providers()
    if not providers:
        _cache.cancel_in_flight(
            request.sentence, request.target_language, request.native_language,
            LLMProviderError("No providers"),
        )
        raise LLMProviderError(
            "No LLM providers available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )

    last_error: Exception | None = None
    max_validation_retries = 2

    for provider in providers:
        for attempt in range(max_validation_retries):
            try:
                logger.info(
                    "[%s] Attempting %s (attempt %d/%d)",
                    request_id,
                    provider.name,
                    attempt + 1,
                    max_validation_retries,
                )

                # 3. Generate feedback
                response, usage = await provider.generate_feedback(
                    request.sentence,
                    request.target_language,
                    request.native_language,
                )

                # Track token usage
                _total_usage["input_tokens"] += usage.input_tokens
                _total_usage["output_tokens"] += usage.output_tokens
                _total_usage["requests"] += 1

                # 4. Sentinel validation
                validation = validate_response(request, response)
                if not validation:
                    logger.warning(
                        "[%s] Sentinel validation failed on attempt %d: %s",
                        request_id,
                        attempt + 1,
                        "; ".join(validation.issues),
                    )
                    if attempt < max_validation_retries - 1:
                        continue  # Retry with same provider
                    else:
                        # Accept the response anyway if structurally valid
                        # (Pydantic already validated the schema)
                        logger.warning(
                            "[%s] Accepting response with validation warnings",
                            request_id,
                        )

                # 4.5 Explanation language check (Self-Refine pattern)
                # Detect if explanations were written in target language
                # instead of native language, and retry with reflexion if so.
                if response.errors:
                    wrong_indices = check_explanation_language(
                        response, request.native_language
                    )
                    if wrong_indices is not None:
                        logger.info(
                            "[%s] Explanation language mismatch at indices %s — "
                            "triggering reflexion retry",
                            request_id,
                            wrong_indices,
                        )
                        try:
                            reflexion_response, reflexion_usage = (
                                await provider.generate_reflexion_feedback(
                                    request.sentence,
                                    request.target_language,
                                    request.native_language,
                                    response,
                                    wrong_indices,
                                )
                            )
                            _total_usage["input_tokens"] += reflexion_usage.input_tokens
                            _total_usage["output_tokens"] += reflexion_usage.output_tokens
                            _total_usage["requests"] += 1
                            response = reflexion_response
                            logger.info(
                                "[%s] Reflexion retry succeeded — explanations corrected",
                                request_id,
                            )
                        except Exception as e:
                            # Reflexion retry failed — use original response
                            logger.warning(
                                "[%s] Reflexion retry failed: %s — using original",
                                request_id,
                                str(e),
                            )

                # 5. Quality scoring (deterministic, no extra LLM call)
                quality = score_response(request, response)
                elapsed = time.time() - start_time
                get_metrics_tracker().record(
                    request.target_language, quality, len(response.errors),
                    latency_seconds=elapsed,
                )

                # 6. Cache and return
                await _cache.put(
                    request.sentence,
                    request.target_language,
                    request.native_language,
                    response,
                )

                # Resolve in-flight future for any waiting requests
                _cache.resolve_in_flight(
                    request.sentence, request.target_language,
                    request.native_language, response,
                )

                logger.info(
                    "[%s] Feedback via %s in %.3fs | tokens: %d in / %d out | "
                    "quality: %.2f | cache: %s",
                    request_id,
                    provider.name,
                    elapsed,
                    usage.input_tokens,
                    usage.output_tokens,
                    quality.overall_score,
                    _cache.stats,
                )
                return response

            except LLMProviderError as e:
                last_error = e
                logger.warning(
                    "[%s] Provider %s failed: %s", request_id, provider.name, str(e)
                )
                break  # Move to next provider

            except Exception as e:
                last_error = e
                logger.error(
                    "[%s] Unexpected error with %s: %s",
                    request_id,
                    provider.name,
                    str(e),
                )
                break  # Move to next provider

    # All providers failed — cancel in-flight and return localized fallback
    error = LLMProviderError(f"All LLM providers failed. Last error: {last_error}")
    _cache.cancel_in_flight(
        request.sentence, request.target_language, request.native_language, error,
    )

    # Graceful degradation: return localized fallback instead of crashing
    logger.error(
        "[%s] All providers failed. Returning localized fallback response. "
        "Last error: %s",
        request_id,
        str(last_error),
    )
    return build_fallback_response(request.sentence, request.native_language)


def get_cache_stats() -> dict:
    """Return cache statistics for the health endpoint."""
    return _cache.stats


def get_usage_stats() -> dict:
    """Return cumulative token usage statistics."""
    return dict(_total_usage)
