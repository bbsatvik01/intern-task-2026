"""SSE streaming endpoint for real-time feedback delivery.

Uses FastAPI StreamingResponse with text/event-stream content type.
Sends status events during processing and the final JSON response
as a data event. Includes keep-alive heartbeat.

Design decisions:
- Status events give instant feedback (processing, validating, complete)
- Final response is identical to POST /feedback (same schema)
- Error events provide graceful degradation
- No extra dependencies (uses FastAPI built-in StreamingResponse)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models import FeedbackRequest
from app.feedback import get_feedback
from app.providers import LLMProviderError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _feedback_event_generator(request: FeedbackRequest):
    """Async generator that yields SSE events during feedback processing.

    Event types:
    - status: Processing stage updates (processing, validating, complete)
    - data: Final feedback response (JSON)
    - error: Error information if processing fails
    """
    start_time = time.time()

    # Send initial status
    yield _format_sse_event("status", {"stage": "processing", "message": "Analyzing your sentence..."})
    await asyncio.sleep(0)  # Yield control to event loop

    try:
        # Generate feedback using existing pipeline
        response = await get_feedback(request)

        elapsed = round(time.time() - start_time, 2)

        # Send completion status
        yield _format_sse_event("status", {
            "stage": "complete",
            "message": "Analysis complete",
            "elapsed_seconds": elapsed,
        })

        # Send the actual response data
        yield _format_sse_event("data", response.model_dump())

        # Send done signal
        yield _format_sse_event("done", {"elapsed_seconds": elapsed})

    except LLMProviderError as e:
        yield _format_sse_event("error", {
            "message": str(e),
            "type": "provider_error",
        })

    except Exception as e:
        logger.error("Streaming error: %s", str(e))
        yield _format_sse_event("error", {
            "message": "An unexpected error occurred",
            "type": "internal_error",
        })


def _format_sse_event(event_type: str, data: dict) -> str:
    """Format data as a Server-Sent Event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


@router.post("/feedback/stream")
async def stream_feedback(request: FeedbackRequest):
    """Stream language feedback as Server-Sent Events.

    Provides real-time status updates during processing:
    - event: status — Processing stage (processing, validating, complete)
    - event: data — Final feedback response (same schema as POST /feedback)
    - event: error — Error details if processing fails
    - event: done — Signal that streaming is complete

    This is ideal for frontend applications that want to show progress
    indicators to users while the LLM processes their input.
    """
    return StreamingResponse(
        _feedback_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
