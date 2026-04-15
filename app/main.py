"""FastAPI application with production-grade middleware, endpoints, and monitoring.

Production features:
- Structured JSON logging with correlation IDs
- Per-IP rate limiting (sliding window, configurable)
- SSE streaming endpoint for real-time feedback
- Paragraph-level analysis for multi-sentence text
- Async job queue with polling for traffic spikes
- Quality metrics tracking per language with p95/p99 latency
- Request/response logging with latency tracking
"""

import logging
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.feedback import get_cache_stats, get_feedback, get_usage_stats
from app.logging_config import RequestLoggingMiddleware, setup_logging
from app.metrics import get_metrics_tracker
from app.models import FeedbackRequest, FeedbackResponse
from app.paragraph import router as paragraph_router
from app.providers import LLMProviderError
from app.rate_limiter import RateLimitMiddleware, get_rate_limiter
from app.async_queue import get_job_queue
from app.async_queue import router as async_router
from app.streaming import router as streaming_router
from app.voice_tutor import router as voice_tutor_router

# Load .env file for local development (Docker passes env vars via docker-compose)
load_dotenv()

# Initialize structured logging BEFORE any loggers are used
setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Language Feedback API",
    description="LLM-powered language correction and feedback for learners",
    version="2.0.0",
)

# --- Middleware (applied in reverse order: last added = outermost) ---
# 1. Request logging with correlation IDs (outermost — captures everything)
app.add_middleware(RequestLoggingMiddleware)
# 2. Rate limiting (before request processing)
app.add_middleware(RateLimitMiddleware)

# --- CORS (needed for WebSocket connections in dev) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(streaming_router)
app.include_router(paragraph_router)
app.include_router(async_router)
app.include_router(voice_tutor_router)

# --- Static files for voice tutor UI ---
import os as _os

_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint returning API status, cache, usage, and rate limit stats."""
    return {
        "status": "healthy",
        "cache": get_cache_stats(),
        "token_usage": get_usage_stats(),
        "rate_limiter": get_rate_limiter().stats,
        "job_queue": get_job_queue().get_stats(),
    }


@app.get("/metrics")
async def metrics_endpoint():
    """Quality metrics endpoint showing per-language accuracy tracking.

    Returns aggregate quality scores, error counts, and accuracy rates
    for each language that has been processed. Useful for monitoring
    LLM output quality over time.
    """
    tracker = get_metrics_tracker()
    return tracker.get_stats()


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


# --- Voice Tutor UI page ---
@app.get("/voice-tutor")
async def voice_tutor_page():
    """Serve the voice tutor single-page application."""
    return FileResponse(
        _os.path.join(_static_dir, "index.html"),
        media_type="text/html",
    )
