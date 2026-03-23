"""Pydantic models for request/response validation with strict type enforcement.

Features:
- Literal types for compile-time enum safety (error_type, difficulty)
- ConfigDict(extra='forbid') rejects unexpected LLM output fields
- Error type alias mapping normalizes common LLM mislabels
- model_validator ensures is_correct/errors consistency
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Strict enum types matching the JSON schema
ErrorType = Literal[
    "grammar",
    "spelling",
    "word_choice",
    "punctuation",
    "word_order",
    "missing_word",
    "extra_word",
    "conjugation",
    "gender_agreement",
    "number_agreement",
    "tone_register",
    "other",
]

CEFRLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2"]

# Error type alias mapping: normalizes common LLM mislabels to valid types.
# This handles cases where the model returns plausible but non-standard types.
ERROR_TYPE_ALIASES: dict[str, str] = {
    "verb_conjugation": "conjugation",
    "tense": "conjugation",
    "verb_form": "conjugation",
    "particle": "grammar",
    "article": "grammar",
    "case": "grammar",
    "syntax": "grammar",
    "preposition": "word_choice",
    "vocabulary": "word_choice",
    "register": "tone_register",
    "formality": "tone_register",
    "typo": "spelling",
    "accent": "spelling",
    "diacritic": "spelling",
    "redundant": "extra_word",
    "unnecessary": "extra_word",
    "omission": "missing_word",
    "missing": "missing_word",
    "plural": "number_agreement",
    "gender": "gender_agreement",
}

VALID_ERROR_TYPES = set(ErrorType.__args__)  # type: ignore[attr-defined]


class ErrorDetail(BaseModel):
    """A single error found in the learner's sentence."""

    model_config = ConfigDict(extra="forbid")

    original: str = Field(
        description="The erroneous word or phrase from the original sentence"
    )
    correction: str = Field(description="The corrected word or phrase")
    error_type: ErrorType = Field(description="Category of the error")
    explanation: str = Field(
        description="A brief, learner-friendly explanation written in the native language"
    )

    @field_validator("error_type", mode="before")
    @classmethod
    def normalize_error_type(cls, v: str) -> str:
        """Normalize common LLM mislabels to valid error types."""
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in VALID_ERROR_TYPES:
                return normalized
            if normalized in ERROR_TYPE_ALIASES:
                return ERROR_TYPE_ALIASES[normalized]
            # Unknown type → default to 'other'
            return "other"
        return v


class FeedbackRequest(BaseModel):
    """Incoming request to analyze a learner's sentence."""

    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(
        min_length=1,
        max_length=5000,
        description="The learner's sentence in the target language",
    )
    target_language: str = Field(
        min_length=2, description="The language the learner is studying"
    )
    native_language: str = Field(
        min_length=2,
        description="The learner's native language -- explanations will be in this language",
    )


class FeedbackResponse(BaseModel):
    """Structured feedback response conforming to the JSON schema."""

    model_config = ConfigDict(extra="forbid")

    corrected_sentence: str = Field(
        description="The grammatically corrected version of the input sentence"
    )
    is_correct: bool = Field(description="true if the original sentence had no errors")
    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="List of errors found. Empty if the sentence is correct.",
    )
    difficulty: CEFRLevel = Field(
        description="CEFR difficulty level: A1, A2, B1, B2, C1, or C2"
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "FeedbackResponse":
        """Sentinel validation: ensure is_correct is consistent with errors list."""
        if self.is_correct and len(self.errors) > 0:
            # Auto-fix: if marked correct but has errors, trust the errors
            object.__setattr__(self, "is_correct", False)
        if not self.is_correct and len(self.errors) == 0:
            # Auto-fix: if marked incorrect but no errors listed, trust is_correct
            object.__setattr__(self, "is_correct", True)
        return self
