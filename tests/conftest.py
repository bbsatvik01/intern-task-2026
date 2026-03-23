"""Shared test fixtures for the Language Feedback API test suite.

This module provides reusable fixtures and helpers used across unit,
integration, and schema test files. This pattern (conftest.py) ensures
DRY test configuration and is the pytest-recommended approach.
"""

import os
from typing import Any

import pytest


# --- API Client Fixture ---

@pytest.fixture
def client():
    """FastAPI test client for endpoint-level testing."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


# --- Sample Request Fixtures ---

@pytest.fixture
def spanish_error_request() -> dict[str, str]:
    """Spanish conjugation error test case."""
    return {
        "sentence": "Yo soy fue al mercado ayer.",
        "target_language": "Spanish",
        "native_language": "English",
    }


@pytest.fixture
def german_correct_request() -> dict[str, str]:
    """Correct German sentence — should return is_correct=True."""
    return {
        "sentence": "Ich habe gestern einen interessanten Film gesehen.",
        "target_language": "German",
        "native_language": "English",
    }


@pytest.fixture
def japanese_particle_request() -> dict[str, str]:
    """Japanese particle error (を→に)."""
    return {
        "sentence": "私は東京を住んでいます。",
        "target_language": "Japanese",
        "native_language": "English",
    }


@pytest.fixture
def french_multi_error_request() -> dict[str, str]:
    """French sentence with multiple errors."""
    return {
        "sentence": "Je suis allé à le magasin pour acheter des pomme.",
        "target_language": "French",
        "native_language": "English",
    }


@pytest.fixture
def arabic_rtl_request() -> dict[str, str]:
    """Arabic RTL script test case."""
    return {
        "sentence": "أنا ذهبت إلي المدرسة أمس.",
        "target_language": "Arabic",
        "native_language": "English",
    }


@pytest.fixture
def korean_correct_request() -> dict[str, str]:
    """Correct Korean sentence."""
    return {
        "sentence": "오늘 날씨가 정말 좋습니다.",
        "target_language": "Korean",
        "native_language": "English",
    }


# --- Response Validation Helpers ---

def assert_valid_response(data: dict[str, Any], expected_correct: bool | None = None) -> None:
    """Assert that a response matches the FeedbackResponse schema.

    Args:
        data: Response JSON dict to validate
        expected_correct: If set, assert is_correct matches this value
    """
    assert "corrected_sentence" in data, "Missing corrected_sentence"
    assert "is_correct" in data, "Missing is_correct"
    assert "errors" in data, "Missing errors"
    assert "difficulty" in data, "Missing difficulty"

    assert isinstance(data["is_correct"], bool), "is_correct must be bool"
    assert isinstance(data["errors"], list), "errors must be a list"
    assert data["difficulty"] in {"A1", "A2", "B1", "B2", "C1", "C2"}, \
        f"Invalid difficulty: {data['difficulty']}"

    # Consistency check: is_correct ↔ errors
    if data["is_correct"]:
        assert len(data["errors"]) == 0, \
            "is_correct=True but errors list is non-empty"
    if not data["is_correct"]:
        assert len(data["errors"]) > 0, \
            "is_correct=False but errors list is empty"

    # Validate each error entry
    valid_types = {
        "grammar", "spelling", "word_choice", "punctuation", "word_order",
        "missing_word", "extra_word", "conjugation", "gender_agreement",
        "number_agreement", "tone_register", "other",
    }
    for error in data["errors"]:
        assert "original" in error, "Error missing 'original' field"
        assert "correction" in error, "Error missing 'correction' field"
        assert "error_type" in error, "Error missing 'error_type' field"
        assert "explanation" in error, "Error missing 'explanation' field"
        assert error["error_type"] in valid_types, \
            f"Invalid error_type: {error['error_type']}"
        assert len(error["explanation"]) > 10, \
            f"Explanation too short ({len(error['explanation'])} chars)"

    if expected_correct is not None:
        assert data["is_correct"] == expected_correct, \
            f"Expected is_correct={expected_correct}, got {data['is_correct']}"


# --- Test Skip Helpers ---

def requires_api_key(provider: str = "openai") -> pytest.MarkDecorator:
    """Skip decorator for tests requiring API keys."""
    env_var = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    return pytest.mark.skipif(
        not os.getenv(env_var),
        reason=f"{env_var} not set — skipping {provider} integration test",
    )
