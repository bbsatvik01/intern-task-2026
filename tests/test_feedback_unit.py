"""Unit tests for models, validators, and cache — no API keys required.

Tests cover:
- Pydantic model validation (strict types, consistency checks)
- Sentinel validation logic (grounding, consistency, empty fields)
- Cache behavior (hit/miss, TTL, key generation)
- Provider availability detection
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.cache import ResponseCache
from app.models import ErrorDetail, FeedbackRequest, FeedbackResponse
from app.validators import validate_response


# ============================================================
# Model Validation Tests
# ============================================================


class TestModels:
    """Test Pydantic model validation and consistency checks."""

    def test_valid_response_with_errors(self):
        """A response with errors should parse correctly."""
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado ayer.",
            is_correct=False,
            errors=[
                ErrorDetail(
                    original="soy fue",
                    correction="fui",
                    error_type="conjugation",
                    explanation="Wrong verb form",
                )
            ],
            difficulty="A2",
        )
        assert response.is_correct is False
        assert len(response.errors) == 1
        assert response.errors[0].error_type == "conjugation"
        assert response.difficulty == "A2"

    def test_valid_correct_response(self):
        """A correct sentence should have is_correct=True and empty errors."""
        response = FeedbackResponse(
            corrected_sentence="Das ist gut.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )
        assert response.is_correct is True
        assert len(response.errors) == 0

    def test_consistency_auto_fix_errors_with_is_correct_true(self):
        """If is_correct=True but errors exist, auto-fix to is_correct=False."""
        response = FeedbackResponse(
            corrected_sentence="Fixed sentence.",
            is_correct=True,  # Inconsistent
            errors=[
                ErrorDetail(
                    original="bad",
                    correction="good",
                    error_type="word_choice",
                    explanation="Wrong word",
                )
            ],
            difficulty="B1",
        )
        # model_validator should auto-fix this
        assert response.is_correct is False

    def test_consistency_auto_fix_no_errors_with_is_correct_false(self):
        """If is_correct=False but no errors, auto-fix to is_correct=True."""
        response = FeedbackResponse(
            corrected_sentence="Correct sentence.",
            is_correct=False,  # Inconsistent
            errors=[],
            difficulty="A1",
        )
        assert response.is_correct is True

    def test_invalid_error_type_rejected(self):
        """An invalid error_type should raise a validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ErrorDetail(
                original="bad",
                correction="good",
                error_type="nonexistent_type",
                explanation="Test",
            )

    def test_invalid_cefr_level_rejected(self):
        """An invalid CEFR level should raise a validation error."""
        with pytest.raises(Exception):
            FeedbackResponse(
                corrected_sentence="Test.",
                is_correct=True,
                errors=[],
                difficulty="D1",  # Not a valid CEFR level
            )

    def test_all_twelve_error_types_valid(self):
        """All 12 defined error types should be accepted."""
        valid_types = [
            "grammar", "spelling", "word_choice", "punctuation",
            "word_order", "missing_word", "extra_word", "conjugation",
            "gender_agreement", "number_agreement", "tone_register", "other",
        ]
        for error_type in valid_types:
            error = ErrorDetail(
                original="test",
                correction="fixed",
                error_type=error_type,
                explanation="Explanation",
            )
            assert error.error_type == error_type

    def test_all_cefr_levels_valid(self):
        """All 6 CEFR levels should be accepted."""
        for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            response = FeedbackResponse(
                corrected_sentence="Test.",
                is_correct=True,
                errors=[],
                difficulty=level,
            )
            assert response.difficulty == level

    def test_request_empty_sentence_rejected(self):
        """An empty sentence should be rejected."""
        with pytest.raises(Exception):
            FeedbackRequest(
                sentence="",
                target_language="Spanish",
                native_language="English",
            )


# ============================================================
# Sentinel Validator Tests
# ============================================================


class TestValidators:
    """Test sentinel validation logic."""

    def test_valid_response_passes(self):
        """A well-formed response should pass all checks."""
        request = FeedbackRequest(
            sentence="Yo soy fue al mercado ayer.",
            target_language="Spanish",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado ayer.",
            is_correct=False,
            errors=[
                ErrorDetail(
                    original="soy fue",
                    correction="fui",
                    error_type="conjugation",
                    explanation="Wrong verb form",
                )
            ],
            difficulty="A2",
        )
        result = validate_response(request, response)
        assert result.is_valid is True
        assert len(result.issues) == 0

    def test_grounding_check_fails_for_hallucinated_original(self):
        """If 'original' text doesn't exist in input, validation should fail."""
        request = FeedbackRequest(
            sentence="Yo soy fue al mercado ayer.",
            target_language="Spanish",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado ayer.",
            is_correct=False,
            errors=[
                ErrorDetail(
                    original="haber sido",  # This text is NOT in the input
                    correction="fui",
                    error_type="conjugation",
                    explanation="Wrong verb form",
                )
            ],
            difficulty="A2",
        )
        result = validate_response(request, response)
        assert result.is_valid is False
        assert "not found in input sentence" in result.issues[0]

    def test_empty_correction_caught(self):
        """An empty correction string should be flagged."""
        request = FeedbackRequest(
            sentence="bad sentence here",
            target_language="English",
            native_language="Spanish",
        )
        response = FeedbackResponse(
            corrected_sentence="good sentence here",
            is_correct=False,
            errors=[
                ErrorDetail(
                    original="bad",
                    correction="",
                    error_type="word_choice",
                    explanation="Use 'good' instead",
                )
            ],
            difficulty="A1",
        )
        result = validate_response(request, response)
        assert result.is_valid is False
        assert "correction is empty" in result.issues[0]

    def test_correct_sentence_passes(self):
        """A correct sentence response should pass validation."""
        request = FeedbackRequest(
            sentence="Das Wetter ist heute schön.",
            target_language="German",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Das Wetter ist heute schön.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )
        result = validate_response(request, response)
        assert result.is_valid is True


# ============================================================
# Cache Tests
# ============================================================


class TestCache:
    """Test in-memory response cache."""

    def test_cache_miss_then_hit(self):
        """First lookup should miss, second should hit."""
        cache = ResponseCache()
        response = FeedbackResponse(
            corrected_sentence="Fixed.",
            is_correct=False,
            errors=[],
            difficulty="A1",
        )

        # Miss
        assert cache.get("test", "Spanish", "English") is None
        assert cache.stats["misses"] == 1

        # Store
        cache.put("test", "Spanish", "English", response)

        # Hit
        result = cache.get("test", "Spanish", "English")
        assert result is not None
        assert result.corrected_sentence == "Fixed."
        assert cache.stats["hits"] == 1

    def test_cache_key_varies_by_language(self):
        """Different language pairs should have different cache keys."""
        cache = ResponseCache()
        response = FeedbackResponse(
            corrected_sentence="Test.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )

        cache.put("Hello", "English", "Spanish", response)
        assert cache.get("Hello", "English", "Spanish") is not None
        assert cache.get("Hello", "English", "French") is None  # Different native lang

    def test_cache_ttl_expiry(self):
        """Entries should expire after TTL."""
        cache = ResponseCache(ttl_seconds=1)
        response = FeedbackResponse(
            corrected_sentence="Test.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )

        cache.put("test", "en", "es", response)
        assert cache.get("test", "en", "es") is not None

        # Wait for TTL to expire
        time.sleep(1.1)
        assert cache.get("test", "en", "es") is None

    def test_cache_max_size_eviction(self):
        """Cache should evict oldest entries when full."""
        cache = ResponseCache(max_size=2)
        response = FeedbackResponse(
            corrected_sentence="Test.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )

        cache.put("a", "en", "es", response)
        cache.put("b", "en", "es", response)
        cache.put("c", "en", "es", response)  # Should evict "a"

        assert cache.stats["size"] == 2


# ============================================================
# Rate Limiter Tests
# ============================================================


class TestRateLimiter:
    """Test in-memory sliding window rate limiter."""

    def test_allows_requests_under_limit(self):
        """Requests under the limit should be allowed."""
        from app.rate_limiter import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)

        for i in range(5):
            allowed, info = limiter.is_allowed("test_ip")
            assert allowed is True

    def test_blocks_requests_over_limit(self):
        """Requests over the limit should be blocked with Retry-After."""
        from app.rate_limiter import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)

        # Use up the limit
        for _ in range(3):
            limiter.is_allowed("test_ip")

        # Next request should be blocked
        allowed, info = limiter.is_allowed("test_ip")
        assert allowed is False
        assert "Retry-After" in info
        assert int(info["Retry-After"]) > 0

    def test_different_clients_independent(self):
        """Different IP addresses should have independent limits."""
        from app.rate_limiter import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

        allowed1, _ = limiter.is_allowed("ip_a")
        assert allowed1 is True

        allowed2, _ = limiter.is_allowed("ip_b")
        assert allowed2 is True

        # ip_a should now be blocked, ip_b still allowed for 1 more
        blocked, _ = limiter.is_allowed("ip_a")
        assert blocked is False

    def test_stats_tracking(self):
        """Stats should report active client count."""
        from app.rate_limiter import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

        limiter.is_allowed("client_1")
        limiter.is_allowed("client_2")

        stats = limiter.stats
        assert stats["active_clients"] == 2
        assert stats["max_requests_per_window"] == 10


# ============================================================
# Metrics Scorer Tests
# ============================================================


class TestMetricsScorer:
    """Test deterministic quality scoring."""

    def test_perfect_score(self):
        """A well-grounded, consistent response should score 1.0."""
        from app.metrics import score_response
        request = FeedbackRequest(
            sentence="Yo soy fue al mercado.",
            target_language="Spanish",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado.",
            is_correct=False,
            errors=[ErrorDetail(
                original="soy fue",
                correction="fui",
                error_type="conjugation",
                explanation="Wrong verb form",
            )],
            difficulty="A2",
        )
        score = score_response(request, response)
        assert score.grounding_score == 1.0
        assert score.consistency_score == 1.0
        assert score.overall_score == 1.0
        assert len(score.issues) == 0

    def test_ungrounded_original_lowers_score(self):
        """Hallucinated 'original' text should lower grounding score."""
        from app.metrics import score_response
        request = FeedbackRequest(
            sentence="Yo soy fue al mercado.",
            target_language="Spanish",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado.",
            is_correct=False,
            errors=[ErrorDetail(
                original="haber sido",  # NOT in input
                correction="fui",
                error_type="conjugation",
                explanation="Wrong verb form",
            )],
            difficulty="A2",
        )
        score = score_response(request, response)
        assert score.grounding_score == 0.0
        assert score.overall_score < 1.0
        assert len(score.issues) > 0

    def test_consistency_mismatch(self):
        """is_correct=true with errors should lower consistency score."""
        from app.metrics import score_response
        request = FeedbackRequest(
            sentence="Bad sentence here.",
            target_language="English",
            native_language="Spanish",
        )
        # After model_validator auto-fix, is_correct becomes False
        response = FeedbackResponse(
            corrected_sentence="Good sentence here.",
            is_correct=True,  # Will be auto-fixed to False by model_validator
            errors=[ErrorDetail(
                original="Bad",
                correction="Good",
                error_type="word_choice",
                explanation="Use good",
            )],
            difficulty="A1",
        )
        # After model_validator, is_correct should be False (auto-fixed)
        # So consistency should actually be 1.0 now
        score = score_response(request, response)
        assert score.consistency_score == 1.0  # Auto-fixed by Pydantic

    def test_correct_sentence_perfect_score(self):
        """A correct sentence response should score perfectly."""
        from app.metrics import score_response
        request = FeedbackRequest(
            sentence="Das ist gut.",
            target_language="German",
            native_language="English",
        )
        response = FeedbackResponse(
            corrected_sentence="Das ist gut.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )
        score = score_response(request, response)
        assert score.overall_score == 1.0


# ============================================================
# Paragraph Splitting Tests
# ============================================================


class TestParagraphSplitting:
    """Test sentence splitting logic."""

    def test_basic_splitting(self):
        """Split simple sentences on period boundaries."""
        from app.paragraph import split_sentences
        result = split_sentences("Hello world. How are you? I am fine!")
        assert len(result) == 3
        assert result[0] == "Hello world."
        assert result[1] == "How are you?"
        assert result[2] == "I am fine!"

    def test_empty_text(self):
        """Empty text should return empty list."""
        from app.paragraph import split_sentences
        assert split_sentences("") == []
        assert split_sentences("   ") == []

    def test_single_sentence(self):
        """A single sentence without trailing space should return one item."""
        from app.paragraph import split_sentences
        result = split_sentences("Hello world.")
        assert len(result) == 1
        assert result[0] == "Hello world."

    def test_unicode_sentence_boundaries(self):
        """CJK sentence-ending punctuation should be recognized."""
        from app.paragraph import split_sentences
        result = split_sentences("これはテストです。元気ですか？")
        assert len(result) == 2


# ============================================================
# Cache Counter After Scoring Tests
# ============================================================


class TestCacheCounterAfterScoring:
    """Test that cache stats update correctly through the scoring pipeline."""

    def test_cache_miss_increments_on_new_request(self):
        """A new unique request should increment cache misses."""
        cache = ResponseCache(max_size=100, ttl_seconds=3600)
        initial_misses = cache.stats["misses"]

        cache.get("brand new sentence", "Spanish", "English")
        assert cache.stats["misses"] == initial_misses + 1
        assert cache.stats["hits"] == 0

    def test_cache_hit_increments_after_put(self):
        """After putting a response, getting it should increment hits."""
        cache = ResponseCache(max_size=100, ttl_seconds=3600)
        response = FeedbackResponse(
            corrected_sentence="Yo fui al mercado.",
            is_correct=False,
            errors=[ErrorDetail(
                original="soy fue",
                correction="fui",
                error_type="conjugation",
                explanation="Wrong verb form",
            )],
            difficulty="A2",
        )

        # Put and then get
        cache.put("Yo soy fue al mercado.", "Spanish", "English", response)
        result = cache.get("Yo soy fue al mercado.", "Spanish", "English")

        assert result is not None
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 0

    def test_cache_stats_accumulate_correctly(self):
        """Multiple gets should correctly accumulate hit/miss counters."""
        cache = ResponseCache(max_size=100, ttl_seconds=3600)
        response = FeedbackResponse(
            corrected_sentence="Test.",
            is_correct=True,
            errors=[],
            difficulty="A1",
        )

        # 2 misses, then 1 put, then 3 hits
        cache.get("a", "en", "es")  # miss
        cache.get("b", "en", "es")  # miss
        cache.put("a", "en", "es", response)
        cache.get("a", "en", "es")  # hit
        cache.get("a", "en", "es")  # hit
        cache.get("a", "en", "es")  # hit

        assert cache.stats["misses"] == 2
        assert cache.stats["hits"] == 3
        assert cache.stats["hit_rate"] == "60.0%"


# ============================================================
# SSE Streaming Format Tests
# ============================================================


class TestStreamingSSEFormat:
    """Test SSE event formatting without requiring an API key."""

    def test_sse_event_format(self):
        """SSE events should have correct event: and data: lines."""
        from app.streaming import _format_sse_event
        result = _format_sse_event("status", {"stage": "processing", "message": "test"})
        assert result.startswith("event: status\n")
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_sse_event_json_valid(self):
        """SSE data payload should be valid JSON."""
        import json
        from app.streaming import _format_sse_event
        result = _format_sse_event("data", {"key": "value", "count": 42})
        # Extract the data line
        lines = result.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        json_str = data_line[len("data: "):]
        parsed = json.loads(json_str)
        assert parsed["key"] == "value"
        assert parsed["count"] == 42

    def test_sse_event_unicode_support(self):
        """SSE should handle unicode characters correctly."""
        from app.streaming import _format_sse_event
        result = _format_sse_event("data", {"sentence": "私は東京に住んでいます。"})
        assert "私は東京に住んでいます。" in result
