"""Explanation language validator using langdetect.

Post-processing validation that detects when an LLM writes explanations
in the target language instead of the learner's native language. When a
mismatch is detected, the reflexion retry system provides the LLM with
its own output and a specific correction instruction.

Design decisions:
- langdetect chosen over lingua (lighter weight, 55 languages, no Rust deps)
- DetectorFactory.seed = 0 for deterministic results across runs
- Only checks explanations > 20 chars (short text detection is unreliable)
- Maps common language names to ISO 639-1 codes for langdetect compatibility
- Returns None (skip check) for languages not in the mapping, avoiding false positives
"""

import logging
from typing import Optional

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException

from app.models import FeedbackResponse

logger = logging.getLogger(__name__)

# Set seed for deterministic detection (langdetect is non-deterministic by default)
DetectorFactory.seed = 0

# Map common language names to ISO 639-1 codes used by langdetect.
# This mapping covers the 15+ languages our API is tested with.
LANGUAGE_TO_ISO = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh-cn",
    "mandarin": "zh-cn",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "turkish": "tr",
    "thai": "th",
    "vietnamese": "vi",
    "dutch": "nl",
    "polish": "pl",
    "swedish": "sv",
    "indonesian": "id",
    "greek": "el",
    "hebrew": "he",
    "czech": "cs",
    "romanian": "ro",
    "hungarian": "hu",
    "finnish": "fi",
    "danish": "da",
    "norwegian": "no",
    "ukrainian": "uk",
    "tagalog": "tl",
    "malay": "ms",
    "persian": "fa",
    "farsi": "fa",
    "bengali": "bn",
    "tamil": "ta",
    "telugu": "te",
    "urdu": "ur",
    "swahili": "sw",
}

# Minimum explanation length for reliable language detection.
# Short texts (< 20 chars) have high false positive rates with langdetect.
MIN_DETECTION_LENGTH = 20


def _get_iso_code(language_name: str) -> Optional[str]:
    """Convert a language name to its ISO 639-1 code.

    Returns None if the language is not in our mapping (avoids false positives).
    """
    return LANGUAGE_TO_ISO.get(language_name.lower().strip())


def check_explanation_language(
    response: FeedbackResponse, native_language: str
) -> Optional[list[int]]:
    """Check if explanations are written in the correct (native) language.

    Returns:
        List of error indices whose explanations are in the WRONG language,
        or None if all explanations are in the correct language or check is skipped.
    """
    expected_iso = _get_iso_code(native_language)
    if expected_iso is None:
        # Unknown language — skip check to avoid false positives
        logger.debug(
            "Skipping explanation language check: '%s' not in mapping",
            native_language,
        )
        return None

    wrong_indices: list[int] = []

    for i, error in enumerate(response.errors):
        explanation = error.explanation.strip()

        # Skip short explanations — langdetect is unreliable under 20 chars
        if len(explanation) < MIN_DETECTION_LENGTH:
            continue

        try:
            detected = detect(explanation)

            # langdetect uses "zh-cn"/"zh-tw" but sometimes returns just "zh"
            if expected_iso.startswith("zh") and detected.startswith("zh"):
                continue  # Both are Chinese variants — accept

            if detected != expected_iso:
                logger.info(
                    "Explanation %d language mismatch: expected=%s, detected=%s, "
                    "text=%.50s...",
                    i,
                    expected_iso,
                    detected,
                    explanation,
                )
                wrong_indices.append(i)

        except LangDetectException:
            # Detection failed — skip this explanation (don't penalize)
            logger.debug("langdetect failed on explanation %d, skipping", i)
            continue

    return wrong_indices if wrong_indices else None
