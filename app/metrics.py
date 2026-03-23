"""Custom evaluation metrics for LLM response quality scoring.

Provides per-request quality assessment WITHOUT an additional LLM call.
All checks are deterministic and run in microseconds.

Metrics:
- Grounding score: % of 'original' fields found in input sentence
- Consistency score: is_correct matches errors array
- Completeness score: all required fields non-empty
- Overall quality score: weighted average (0-1.0)
- Per-language accuracy tracking over time
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.models import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality assessment for a single LLM response."""

    grounding_score: float  # 0-1.0: % of originals found in input
    consistency_score: float  # 0 or 1: is_correct matches errors
    completeness_score: float  # 0-1.0: % of fields non-empty
    overall_score: float  # Weighted average
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "grounding_score": round(self.grounding_score, 3),
            "consistency_score": round(self.consistency_score, 3),
            "completeness_score": round(self.completeness_score, 3),
            "overall_score": round(self.overall_score, 3),
            "issues": self.issues,
        }


def score_response(request: FeedbackRequest, response: FeedbackResponse) -> QualityScore:
    """Score an LLM response for quality without an additional LLM call.

    Uses deterministic checks that run in microseconds:
    1. Grounding: Do 'original' fields exist in the input sentence?
    2. Consistency: Does is_correct match the errors array?
    3. Completeness: Are all fields non-empty?

    Returns:
        QualityScore with individual and overall scores (0-1.0)
    """
    issues: list[str] = []

    # 1. Grounding score: % of originals found in input
    if response.errors:
        grounded = sum(1 for e in response.errors if e.original in request.sentence)
        grounding_score = grounded / len(response.errors)
        if grounding_score < 1.0:
            ungrounded = [e.original for e in response.errors if e.original not in request.sentence]
            issues.append(f"Ungrounded originals: {ungrounded}")
    else:
        grounding_score = 1.0  # No errors = perfect grounding

    # 2. Consistency: is_correct matches errors array
    if response.is_correct and len(response.errors) > 0:
        consistency_score = 0.0
        issues.append("is_correct=true but errors exist")
    elif not response.is_correct and len(response.errors) == 0:
        consistency_score = 0.0
        issues.append("is_correct=false but no errors listed")
    else:
        consistency_score = 1.0

    # 3. Completeness: all fields must be non-empty
    total_fields = 0
    filled_fields = 0

    # Check response-level fields
    for field_name in ("corrected_sentence", "difficulty"):
        total_fields += 1
        if getattr(response, field_name, ""):
            filled_fields += 1

    # Check error-level fields
    for error in response.errors:
        for field_name in ("original", "correction", "explanation", "error_type"):
            total_fields += 1
            value = getattr(error, field_name, "")
            if value and str(value).strip():
                filled_fields += 1
            else:
                issues.append(f"Empty field: error.{field_name}")

    completeness_score = filled_fields / total_fields if total_fields > 0 else 1.0

    # Weighted overall score (grounding most important)
    overall_score = (
        grounding_score * 0.5
        + consistency_score * 0.3
        + completeness_score * 0.2
    )

    return QualityScore(
        grounding_score=grounding_score,
        consistency_score=consistency_score,
        completeness_score=completeness_score,
        overall_score=overall_score,
        issues=issues,
    )


class LanguageMetricsTracker:
    """Tracks per-language quality metrics over time.

    Thread-safe for single-process async applications.
    """

    def __init__(self) -> None:
        self._scores: dict[str, list[float]] = defaultdict(list)
        self._request_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._start_time = time.time()
        self._latency_tracker = LatencyTracker()

    def record(self, language: str, quality_score: QualityScore,
               error_count: int, latency_seconds: float = 0.0) -> None:
        """Record a quality score and latency for a language."""
        self._scores[language].append(quality_score.overall_score)
        self._request_counts[language] += 1
        self._error_counts[language] += error_count
        if latency_seconds > 0:
            self._latency_tracker.record(latency_seconds)

    def get_stats(self) -> dict:
        """Return per-language quality statistics with latency percentiles."""
        stats: dict = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "latency": self._latency_tracker.get_percentiles(),
            "languages": {},
        }

        for lang, scores in self._scores.items():
            if scores:
                stats["languages"][lang] = {
                    "requests": self._request_counts[lang],
                    "avg_quality_score": round(sum(scores) / len(scores), 3),
                    "min_quality_score": round(min(scores), 3),
                    "total_errors_detected": self._error_counts[lang],
                    "avg_errors_per_request": round(
                        self._error_counts[lang] / self._request_counts[lang], 2
                    ),
                }

        return stats


class LatencyTracker:
    """Tracks request latencies and computes percentiles (p50/p95/p99).

    Uses a bounded sorted list (last N requests) to compute percentiles
    without external dependencies. Memory-efficient: stores at most
    max_samples float values (~8KB for 1000 samples).

    For production at scale, this would be replaced by Prometheus histograms
    or OpenTelemetry metrics. This implementation demonstrates SLO awareness
    without adding infrastructure dependencies.
    """

    def __init__(self, max_samples: int = 1000) -> None:
        self._latencies: list[float] = []
        self._max_samples = max_samples
        self._total_requests = 0
        self._slo_violations = 0  # Requests exceeding 30s
        self._slo_threshold = 30.0  # seconds

    def record(self, latency_seconds: float) -> None:
        """Record a single request latency."""
        self._total_requests += 1
        if latency_seconds > self._slo_threshold:
            self._slo_violations += 1

        self._latencies.append(latency_seconds)
        # Keep bounded to prevent unbounded memory growth
        if len(self._latencies) > self._max_samples:
            self._latencies.pop(0)  # Remove oldest

    def _percentile(self, p: float) -> float:
        """Compute the p-th percentile from stored latencies.

        Uses the nearest-rank method for simplicity and correctness.
        """
        if not self._latencies:
            return 0.0
        sorted_latencies = sorted(self._latencies)
        index = max(0, int(len(sorted_latencies) * p / 100) - 1)
        return round(sorted_latencies[index], 3)

    def get_percentiles(self) -> dict:
        """Return latency percentiles and SLO tracking data."""
        return {
            "total_requests": self._total_requests,
            "p50_seconds": self._percentile(50),
            "p95_seconds": self._percentile(95),
            "p99_seconds": self._percentile(99),
            "slo_threshold_seconds": self._slo_threshold,
            "slo_violations": self._slo_violations,
            "slo_compliance_rate": (
                round(
                    (self._total_requests - self._slo_violations)
                    / self._total_requests
                    * 100,
                    2,
                )
                if self._total_requests > 0
                else 100.0
            ),
        }


# Module-level singleton
_tracker = LanguageMetricsTracker()


def get_metrics_tracker() -> LanguageMetricsTracker:
    """Get the singleton metrics tracker."""
    return _tracker
