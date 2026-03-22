"""FastAPI application with production-grade error handling and endpoints."""

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.feedback import get_cache_stats, get_feedback
from app.models import FeedbackRequest, FeedbackResponse
from app.providers import LLMProviderError

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Language Feedback API",
    description="LLM-powered language correction and feedback for learners",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint returning API status and cache statistics."""
    return {
        "status": "healthy",
        "cache": get_cache_stats(),
    }


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(request: FeedbackRequest):
    """Analyze a learner's sentence and return structured feedback.

    Takes a sentence in the target language, identifies errors, provides
    corrections with explanations in the learner's native language,
    and assesses sentence difficulty using CEFR levels.
    """
    start_time = time.time()
    logger.info(
        "Feedback request: lang=%s, native=%s, len=%d",
        request.target_language,
        request.native_language,
        len(request.sentence),
    )

    try:
        response = await get_feedback(request)
        elapsed = time.time() - start_time
        logger.info(
            "Feedback response: is_correct=%s, errors=%d, difficulty=%s, time=%.3fs",
            response.is_correct,
            len(response.errors),
            response.difficulty,
            elapsed,
        )
        return response

    except LLMProviderError as e:
        elapsed = time.time() - start_time
        logger.error("LLM provider error after %.3fs: %s", elapsed, str(e))
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_provider_error",
                "message": "All language model providers are currently unavailable. Please try again later.",
                "elapsed_seconds": round(elapsed, 3),
            },
        )

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Unexpected error after %.3fs: %s", elapsed, str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "An unexpected error occurred while processing your request.",
                "elapsed_seconds": round(elapsed, 3),
            },
        )
