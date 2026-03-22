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
