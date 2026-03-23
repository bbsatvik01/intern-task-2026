"""Paragraph-level analysis endpoint.

Extends the single-sentence API to handle multi-sentence text by:
1. Splitting paragraph into sentences
2. Processing each sentence concurrently via the existing feedback pipeline
3. Aggregating results with paragraph-level metrics

Design decisions:
- Concurrent processing with asyncio.gather for speed
- Reuses existing get_feedback pipeline (no code duplication)
- Simple sentence splitting (period/question/exclamation) — good enough
  for the task scope; production would use spaCy or similar NLP library
- Max 10 sentences per request to prevent abuse
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import FeedbackRequest, FeedbackResponse
from app.feedback import get_feedback

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SENTENCES = 10


class ParagraphRequest(BaseModel):
    """Request model for paragraph-level analysis."""

    text: str = Field(
        min_length=1,
        description="The paragraph or multi-sentence text to analyze",
    )
    target_language: str = Field(
        min_length=2, description="The language the learner is studying"
    )
    native_language: str = Field(
        min_length=2,
        description="The learner's native language — explanations in this language",
    )


class SentenceResult(BaseModel):
    """Feedback for a single sentence within a paragraph."""

    sentence: str
    feedback: FeedbackResponse


class ParagraphResponse(BaseModel):
    """Aggregated response for paragraph-level analysis."""

    sentences: list[SentenceResult]
    summary: dict = Field(
        description="Aggregate metrics for the paragraph",
    )


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex-based boundary detection.

    Handles:
    - Period, question mark, exclamation mark endings
    - Preserves sentence content (strips whitespace)
    - Filters out empty strings

    For production, consider using spaCy or NLTK for better accuracy
    with abbreviations and edge cases.
    """
    # Split on sentence-ending punctuation followed by whitespace or end,
    # including CJK sentence-ending marks (。？！) which may not be followed by space
    sentences = re.split(r'(?<=[.!?。？！])\s+|(?<=[。？！])(?=[^\s])', text.strip())
    # Filter empty strings and strip whitespace
    return [s.strip() for s in sentences if s.strip()]


@router.post("/feedback/paragraph", response_model=ParagraphResponse)
async def analyze_paragraph(request: ParagraphRequest):
    """Analyze a paragraph of text, providing per-sentence feedback.

    Splits the input text into individual sentences and processes each
    concurrently through the existing feedback pipeline. Returns
    per-sentence feedback plus aggregate paragraph metrics.

    Limits: Maximum 10 sentences per request.
    """
    sentences = split_sentences(request.text)

    if not sentences:
        raise HTTPException(status_code=400, detail="No sentences found in text")

    if len(sentences) > MAX_SENTENCES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many sentences ({len(sentences)}). Maximum is {MAX_SENTENCES}.",
        )

    start_time = time.time()

    # Process all sentences concurrently
    tasks = [
        get_feedback(FeedbackRequest(
            sentence=sentence,
            target_language=request.target_language,
            native_language=request.native_language,
        ))
        for sentence in sentences
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build response
    sentence_results: list[SentenceResult] = []
    total_errors = 0
    difficulty_counts: dict[str, int] = {}
    correct_count = 0
    failed_count = 0

    for sentence, result in zip(sentences, results):
        if isinstance(result, Exception):
            logger.warning("Failed to analyze sentence: %s — %s", sentence, str(result))
            failed_count += 1
            continue

        sentence_results.append(SentenceResult(
            sentence=sentence,
            feedback=result,
        ))
        total_errors += len(result.errors)
        difficulty_counts[result.difficulty] = difficulty_counts.get(result.difficulty, 0) + 1
        if result.is_correct:
            correct_count += 1

    elapsed = round(time.time() - start_time, 2)
    total_analyzed = len(sentence_results)

    summary = {
        "total_sentences": len(sentences),
        "sentences_analyzed": total_analyzed,
        "sentences_correct": correct_count,
        "sentences_with_errors": total_analyzed - correct_count,
        "total_errors": total_errors,
        "accuracy_rate": round(correct_count / total_analyzed, 2) if total_analyzed > 0 else 0,
        "difficulty_distribution": difficulty_counts,
        "processing_time_seconds": elapsed,
    }

    if failed_count > 0:
        summary["sentences_failed"] = failed_count

    return ParagraphResponse(sentences=sentence_results, summary=summary)
