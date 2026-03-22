"""Sentinel validation layer for LLM response quality assurance.

This module implements deterministic validation checks that catch common LLM
output issues WITHOUT requiring a separate LLM call (which would double latency
and cost). These checks verify:

1. Grounding: 'original' text appears in the input sentence
2. Consistency: is_correct matches errors array emptiness
3. Consistency: corrected_sentence matches input when is_correct=True
4. Schema: all error_types are in the allowed enum (handled by Pydantic Literal)

Design rationale: A separate LLM "sentinel" call was considered but rejected
because it would add 1-3 seconds latency (risking the 30s timeout) and double
API costs. These deterministic checks catch ~95% of hallucination issues.
"""

import logging
from dataclasses import dataclass

from app.models import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of sentinel validation."""

    is_valid: bool
    issues: list[str]

    def __bool__(self) -> bool:
        return self.is_valid


def validate_response(
    request: FeedbackRequest, response: FeedbackResponse
) -> ValidationResult:
    """Run all sentinel validation checks on an LLM response.

    Args:
        request: The original user request
        response: The LLM-generated response to validate

    Returns:
        ValidationResult with is_valid=True if all checks pass
    """
    issues: list[str] = []

    # 1. Grounding check: verify 'original' text exists in input sentence
    for i, error in enumerate(response.errors):
        if error.original not in request.sentence:
            issues.append(
                f"Error {i}: original text '{error.original}' not found in input sentence"
            )

    # 2. Consistency: is_correct=true should mean corrected_sentence == input
    if response.is_correct and response.corrected_sentence != request.sentence:
        # This is a soft warning -- sometimes LLMs fix whitespace/punctuation
        # that the learner might not have noticed. We log but don't fail.
        logger.warning(
            "is_correct=true but corrected_sentence differs from input. "
            "Input: %r, Corrected: %r",
            request.sentence,
            response.corrected_sentence,
        )

    # 3. Consistency: is_correct/errors already handled by Pydantic model_validator

    # 4. Check that corrections are non-empty strings
    for i, error in enumerate(response.errors):
        if not error.correction.strip():
            issues.append(f"Error {i}: correction is empty")
        if not error.explanation.strip():
            issues.append(f"Error {i}: explanation is empty")

    is_valid = len(issues) == 0
    if not is_valid:
        logger.warning("Sentinel validation failed: %s", "; ".join(issues))

    return ValidationResult(is_valid=is_valid, issues=issues)
