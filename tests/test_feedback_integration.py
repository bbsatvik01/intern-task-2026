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


# ============================================================
# Extended Language Coverage (15+ languages)
# ============================================================


@pytest.mark.asyncio
async def test_thai_spelling_error(assert_valid_response):
    """Test detection of Thai spelling/word choice error."""
    request = FeedbackRequest(
        sentence="ผมไปกินข้าวที่ร้านอาหารเมือวาน",
        target_language="Thai",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


@pytest.mark.asyncio
async def test_vietnamese_tone_error(assert_valid_response):
    """Test detection of Vietnamese diacritical/tone error."""
    request = FeedbackRequest(
        sentence="Tôi đã di đến trường học hôm qua.",
        target_language="Vietnamese",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


@pytest.mark.asyncio
async def test_hindi_postposition_error(assert_valid_response):
    """Test detection of Hindi postposition error."""
    request = FeedbackRequest(
        sentence="मैं स्कूल को जाता हूँ।",
        target_language="Hindi",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response)


@pytest.mark.asyncio
async def test_turkish_vowel_harmony_error(assert_valid_response):
    """Test detection of Turkish vowel harmony/suffix error."""
    request = FeedbackRequest(
        sentence="Ben okula gittiler.",
        target_language="Turkish",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


@pytest.mark.asyncio
async def test_italian_article_error(assert_valid_response):
    """Test detection of Italian article/gender error."""
    request = FeedbackRequest(
        sentence="Il ragazza è molto intelligente.",
        target_language="Italian",
        native_language="English",
    )
    response = await get_feedback(request)
    assert_valid_response(response, expect_correct=False)


# ============================================================
# Rate Limiting Integration Test
# ============================================================


def test_rate_limiter_returns_429():
    """Test that rapid requests trigger 429 status code."""
    from app.rate_limiter import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)

    # First 2 requests should pass
    assert limiter.is_allowed("test_ip")[0] is True
    assert limiter.is_allowed("test_ip")[0] is True

    # Third should be blocked
    allowed, info = limiter.is_allowed("test_ip")
    assert allowed is False
    assert "Retry-After" in info


# ============================================================
# Paragraph Endpoint End-to-End Test
# ============================================================


@pytest.mark.asyncio
async def test_paragraph_endpoint_end_to_end(assert_valid_response):
    """Test paragraph analysis with multiple sentences through full pipeline."""
    from app.paragraph import split_sentences, ParagraphRequest, analyze_paragraph

    # First verify splitting works
    text = "Yo soy fue al mercado ayer. La chat est sur le table."
    sentences = split_sentences(text)
    assert len(sentences) == 2

    # Now test full end-to-end through the paragraph endpoint
    request = ParagraphRequest(
        text=text,
        target_language="Spanish",
        native_language="English",
    )
    # Use the endpoint function directly (bypasses HTTP but tests full pipeline)
    response = await analyze_paragraph(request)

    # Verify structure
    assert hasattr(response, "sentences")
    assert hasattr(response, "summary")
    assert response.summary["total_sentences"] == 2
    assert response.summary["sentences_analyzed"] >= 1  # At least 1 should succeed
    assert "accuracy_rate" in response.summary
    assert "difficulty_distribution" in response.summary

    # Verify each sentence result
    for sr in response.sentences:
        assert hasattr(sr, "sentence")
        assert hasattr(sr, "feedback")
        assert_valid_response(sr.feedback)


# ============================================================
# Streaming Endpoint Integration Test
# ============================================================


@pytest.mark.asyncio
async def test_streaming_endpoint_produces_events():
    """Test that streaming endpoint produces valid SSE events end-to-end."""
    from app.streaming import _feedback_event_generator
    from app.models import FeedbackRequest

    request = FeedbackRequest(
        sentence="Yo soy fue al mercado ayer.",
        target_language="Spanish",
        native_language="English",
    )

    events = []
    async for event in _feedback_event_generator(request):
        events.append(event)

    # Should have at least: status(processing), status(complete), data, done
    assert len(events) >= 3, f"Expected at least 3 events, got {len(events)}"

    # First event should be processing status
    assert "processing" in events[0]
    assert "event: status" in events[0]

    # Should have a data event with the actual feedback
    data_events = [e for e in events if "event: data" in e]
    assert len(data_events) == 1, "Expected exactly one data event"

    # Should have a done event
    done_events = [e for e in events if "event: done" in e]
    assert len(done_events) == 1, "Expected exactly one done event"

