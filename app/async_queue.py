"""Asynchronous job queue for non-blocking feedback processing.

Provides queue-based processing for traffic spikes. Clients submit a request
and receive a polling token (job_id). They then poll for the result, which
decouples request submission from LLM processing time.

Architecture:
    POST /feedback/async  →  Returns job_id immediately (~0ms)
    GET  /feedback/jobs/{job_id}  →  Returns status + result when done

Implementation: Uses Python's built-in asyncio for zero-dependency async
processing. For production at scale, the JobQueue interface is designed as
a drop-in replacement for Redis + Celery:

    # Production upgrade path:
    # 1. Replace InMemoryJobQueue with RedisJobQueue
    # 2. Move _process_job to a Celery worker
    # 3. Add Redis service to docker-compose.yml
    # The API surface (submit/poll) stays identical.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from app.feedback import get_feedback
from app.models import FeedbackRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["async"])


class JobStatus(str, Enum):
    """Lifecycle states for an async job."""

    PENDING = "pending"  # Queued, not yet started
    PROCESSING = "processing"  # LLM call in progress
    COMPLETED = "completed"  # Result available
    FAILED = "failed"  # Processing error


@dataclass
class Job:
    """Represents a single async feedback job."""

    id: str
    request: FeedbackRequest
    status: JobStatus = JobStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        """Serialize job state for API response."""
        response: dict[str, Any] = {
            "job_id": self.id,
            "status": self.status.value,
            "created_at": self.created_at,
        }
        if self.status == JobStatus.COMPLETED:
            response["result"] = self.result
            response["completed_at"] = self.completed_at
            response["processing_time_seconds"] = round(
                (self.completed_at or 0) - self.created_at, 3
            )
        elif self.status == JobStatus.FAILED:
            response["error"] = self.error
        return response


class JobQueue:
    """In-memory async job queue with bounded capacity.

    Processes jobs concurrently using asyncio tasks. Bounded to prevent
    memory exhaustion during traffic spikes.

    For production, replace with Redis-backed queue:
        - Jobs stored in Redis hash
        - Processing via Celery workers
        - TTL-based automatic cleanup
    """

    def __init__(self, max_jobs: int = 1000, max_concurrent: int = 10) -> None:
        self._jobs: dict[str, Job] = {}
        self._max_jobs = max_jobs
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cleanup_threshold = max_jobs * 2  # Cleanup when 2x capacity

    async def submit(self, request: FeedbackRequest) -> Job:
        """Submit a new job and start processing in the background.

        Returns immediately with a Job containing the polling token (job_id).
        Raises HTTPException 503 if queue is at capacity.
        """
        # Cleanup old completed jobs if we're over threshold
        if len(self._jobs) >= self._cleanup_threshold:
            self._cleanup_old_jobs()

        if len(self._jobs) >= self._max_jobs:
            raise HTTPException(
                status_code=503,
                detail="Job queue at capacity. Please retry later.",
            )

        job_id = str(uuid.uuid4())[:8]
        job = Job(id=job_id, request=request)
        self._jobs[job_id] = job

        # Fire-and-forget background processing
        asyncio.create_task(self._process_job(job))
        logger.info("Job %s queued for %s", job_id, request.target_language)

        return job

    async def _process_job(self, job: Job) -> None:
        """Process a single job with concurrency limiting."""
        async with self._semaphore:
            job.status = JobStatus.PROCESSING
            try:
                response = await get_feedback(job.request)
                job.result = response.model_dump()
                job.status = JobStatus.COMPLETED
                job.completed_at = time.time()
                logger.info(
                    "Job %s completed in %.3fs",
                    job.id,
                    job.completed_at - job.created_at,
                )
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = time.time()
                logger.error("Job %s failed: %s", job.id, e)

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        return self._jobs.get(job_id)

    def get_stats(self) -> dict:
        """Return queue statistics for monitoring."""
        statuses = {s: 0 for s in JobStatus}
        for job in self._jobs.values():
            statuses[job.status] += 1
        return {
            "total_jobs": len(self._jobs),
            "pending": statuses[JobStatus.PENDING],
            "processing": statuses[JobStatus.PROCESSING],
            "completed": statuses[JobStatus.COMPLETED],
            "failed": statuses[JobStatus.FAILED],
            "capacity": self._max_jobs,
        }

    def _cleanup_old_jobs(self) -> None:
        """Remove completed/failed jobs older than 5 minutes."""
        cutoff = time.time() - 300  # 5 minute TTL
        to_remove = [
            jid
            for jid, job in self._jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
            and (job.completed_at or 0) < cutoff
        ]
        for jid in to_remove:
            del self._jobs[jid]
        if to_remove:
            logger.info("Cleaned up %d old jobs", len(to_remove))


# Module-level singleton
_queue = JobQueue()


def get_job_queue() -> JobQueue:
    """Get the singleton job queue."""
    return _queue


# ---- FastAPI Routes ----


@router.post("/feedback/async")
async def submit_async_feedback(request: FeedbackRequest) -> dict:
    """Submit a feedback request for asynchronous processing.

    Returns immediately with a job_id for polling. Use GET /feedback/jobs/{job_id}
    to check status and retrieve the result when processing completes.

    This endpoint is designed for traffic spikes where you want to decouple
    submission from processing. The synchronous POST /feedback endpoint is
    recommended for interactive use cases where you need the result immediately.
    """
    job = await _queue.submit(request)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "poll_url": f"/feedback/jobs/{job.id}",
        "message": "Job submitted. Poll the poll_url for results.",
    }


@router.get("/feedback/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """Poll for the status and result of an async feedback job.

    Returns:
        - status=pending: Job is queued
        - status=processing: LLM call in progress
        - status=completed: Result available in 'result' field
        - status=failed: Error details in 'error' field
    """
    job = _queue.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found. Jobs expire after 5 minutes.",
        )
    return job.to_dict()
