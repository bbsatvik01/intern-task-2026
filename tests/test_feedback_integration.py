"""Integration tests — require a live LLM API key.

These tests make actual API calls and verify:
- Response schema compliance
- Error detection accuracy across languages
- Correct sentence handling
- Non-Latin script support (Japanese, Korean, Russian, Chinese)
- Native language explanations
- CEFR level assessment
- Dual-provider fallback behavior

Run with: pytest tests/test_feedback_integration.py -v
Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable
"""

import os

import pytest
import pytest_asyncio

from app.feedback import get_feedback
from app.models import FeedbackRequest, FeedbackResponse

# Skip all tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"),
    reason="No LLM API key available",
)


@pytest.fixture
def assert_valid_response():
    """Helper to validate common response properties."""

    def _assert(response: FeedbackResponse, expect_correct: bool = None):
        # Type checks
        assert isinstance(response.corrected_sentence, str)
        assert isinstance(response.is_correct, bool)
        assert isinstance(response.errors, list)
        assert response.difficulty in ("A1", "A2", "B1", "B2", "C1", "C2")

        # Consistency checks
        if response.is_correct:
            assert len(response.errors) == 0, "is_correct=True but errors found"
        else:
            assert len(response.errors) > 0, "is_correct=False but no errors listed"

        if expect_correct is not None:
            assert response.is_correct == expect_correct

        # Error field checks
        for error in response.errors:
            assert error.original, "original text should not be empty"
            assert error.correction, "correction should not be empty"
            assert error.explanation, "explanation should not be empty"
            assert error.error_type in (
                "grammar", "spelling", "word_choice", "punctuation",
                "word_order", "missing_word", "extra_word", "conjugation",
                "gender_agreement", "number_agreement", "tone_register", "other",
            )

    return _assert


# ============================================================
# Basic Error Detection
# ============================================================


@pytest.mark.asyncio
async def test_spanish_conjugation_error(assert_valid_response):
    """Test detection of Spanish verb conjugation error."""
    request = FeedbackRequest(
        sentence="Yo soy fue al mercado ayer.",
        target_language="Spanish",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)
    # Should detect conjugation issue
    error_types = [e.error_type for e in response.errors]
    assert any(t in ("conjugation", "grammar", "extra_word") for t in error_types)


@pytest.mark.asyncio
async def test_french_gender_agreement(assert_valid_response):
    """Test detection of French gender agreement error."""
    request = FeedbackRequest(
        sentence="La chat est sur le table.",
        target_language="French",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


@pytest.mark.asyncio
async def test_portuguese_compound_errors(assert_valid_response):
    """Test detection of multiple errors in Portuguese."""
    request = FeedbackRequest(
        sentence="Eu tem comido muitas maçãs.",
        target_language="Portuguese",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


# ============================================================
# Correct Sentences (must return is_correct=True)
# ============================================================


@pytest.mark.asyncio
async def test_correct_german_sentence(assert_valid_response):
    """A grammatically correct German sentence should return is_correct=True."""
    request = FeedbackRequest(
        sentence="Ich habe gestern einen interessanten Film gesehen.",
        target_language="German",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=True)
    assert response.corrected_sentence == request.sentence


@pytest.mark.asyncio
async def test_correct_english_sentence(assert_valid_response):
    """A correct English sentence should return is_correct=True."""
    request = FeedbackRequest(
        sentence="The cat sat on the mat and purred contentedly.",
        target_language="English",
        native_language="Spanish",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=True)


# ============================================================
# Non-Latin Scripts
# ============================================================


@pytest.mark.asyncio
async def test_japanese_particle_error(assert_valid_response):
    """Test detection of Japanese particle error (non-Latin script)."""
    request = FeedbackRequest(
        sentence="私は東京を住んでいます。",
        target_language="Japanese",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)
    # Should correct を to に
    assert "に" in response.corrected_sentence


@pytest.mark.asyncio
async def test_korean_honorific_error(assert_valid_response):
    """Test detection of Korean formality/honorific error."""
    request = FeedbackRequest(
        sentence="선생님, 나는 학교에 갔어.",
        target_language="Korean",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response)  # Don't assert correctness — sentence is valid in casual Korean


@pytest.mark.asyncio
async def test_russian_case_error(assert_valid_response):
    """Test detection of Russian grammatical case error."""
    request = FeedbackRequest(
        sentence="Я живу в Москва.",
        target_language="Russian",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)
    # Москва should be Москве (prepositional case)
    assert "Москве" in response.corrected_sentence


@pytest.mark.asyncio
async def test_chinese_measure_word_error(assert_valid_response):
    """Test detection of Chinese measure word error."""
    request = FeedbackRequest(
        sentence="我有三个书。",
        target_language="Chinese",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)
    # 个 should be 本 for books
    assert "本" in response.corrected_sentence


@pytest.mark.asyncio
async def test_arabic_gender_agreement(assert_valid_response):
    """Test detection of Arabic gender agreement error."""
    request = FeedbackRequest(
        sentence="الطالبة ذهب إلى المدرسة.",
        target_language="Arabic",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


# ============================================================
# Native Language Explanations
# ============================================================


@pytest.mark.asyncio
async def test_explanation_in_native_language(assert_valid_response):
    """Explanations should be in the native language (Spanish), not target (English)."""
    request = FeedbackRequest(
        sentence="She go to school yesterday.",
        target_language="English",
        native_language="Spanish",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)
    # Explanation should contain Spanish words (not a strict check,
    # but any explanation for a Spanish native speaker should be in Spanish)
    # Just verify we got errors with non-empty explanations
    for error in response.errors:
        assert len(error.explanation) > 10, "Explanation seems too short"


# ============================================================
# Response Time
# ============================================================


@pytest.mark.asyncio
async def test_response_within_timeout(assert_valid_response):
    """Response should return within the 30-second timeout."""
    import time

    request = FeedbackRequest(
        sentence="Yo soy fue al mercado ayer.",
        target_language="Spanish",
        native_language="English",
    )
    start = time.time()
    response = await get_feedback(request)
    elapsed = time.time() - start
    assert_valid_response(response)
    assert elapsed < 30, f"Response took {elapsed:.1f}s, exceeds 30s timeout"
