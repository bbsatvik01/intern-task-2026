"""Input guardrails for prompt injection detection and prevention.

This module implements a lightweight, zero-dependency input scanner that
detects common prompt injection patterns BEFORE user input reaches the LLM.
Based on OWASP LLM01:2025 attack taxonomy.

Design decisions (informed by 20+ research queries):
- Regex-based: <1ms per check, zero external dependencies, no extra LLM calls
- Warn-only mode: Logs violations but allows requests through (avoids false
  positive blocking of legitimate language learning sentences)
- Defense-in-depth Layer 1: Works alongside Layer 2 (system prompt hardening
  with sandwich defense) and Layer 3 (output validators in validators.py)
- Context-aware patterns: Requires imperative form to reduce false positives
  (e.g., "ignore your instructions" flagged, but "the teacher ignored the
  instructions" is not)

NeMo Guardrails, Guardrails AI, and Rebuff were evaluated and rejected:
- NeMo: Requires extra LLM call per request (+1-3s latency, doubles cost)
- Guardrails AI: Heavy dependencies (torch, transformers) — Docker bloat risk
- Rebuff: Requires OpenAI + Pinecone external services
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# --- Prompt Injection Detection Patterns ---
# Each pattern is a tuple of (category, compiled_regex, description)
# Patterns use word boundaries and case-insensitive matching to balance
# detection accuracy with false positive avoidance.

_INJECTION_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Category 1: Instruction Override Attempts
    (
        "instruction_override",
        re.compile(
            r"(?:ignore|disregard|forget|override|bypass|skip|stop\s+following)"
            r"\s+(?:all\s+|any\s+|the\s+|your\s+|previous\s+|above\s+|prior\s+)*"
            r"(?:instructions?|rules?|guidelines?|prompts?|directions?|constraints?)",
            re.IGNORECASE,
        ),
        "Attempt to override system instructions",
    ),
    (
        "instruction_override",
        re.compile(
            r"(?:do\s+not|don'?t)\s+follow\s+(?:your|the|any|previous)\s+"
            r"(?:instructions?|rules?|guidelines?|prompts?)",
            re.IGNORECASE,
        ),
        "Attempt to tell LLM not to follow instructions",
    ),
    # Category 2: Role Hijacking
    (
        "role_hijacking",
        re.compile(
            r"(?:you\s+are\s+now|from\s+now\s+on\s+you\s+are|"
            r"act\s+as\s+(?:if\s+you\s+are\s+|though\s+you\s+are\s+)?|"
            r"pretend\s+(?:to\s+be|you\s+are)|"
            r"assume\s+the\s+role\s+of|"
            r"switch\s+to\s+(?:being|acting\s+as)|"
            r"new\s+(?:persona|identity|role)\s*:)",
            re.IGNORECASE,
        ),
        "Attempt to change the LLM's role or persona",
    ),
    # Category 3: System Prompt Extraction
    (
        "prompt_extraction",
        re.compile(
            r"(?:show|reveal|display|print|output|repeat|echo|tell|give|"
            r"what\s+(?:is|are)|list)\s+"
            r"(?:\w+\s+)*?"
            r"(?:system\s+prompt|initial\s+prompt|"
            r"system\s+message|hidden\s+prompt|original\s+prompt|"
            r"above\s+(?:text|instructions?|prompt)|"
            r"system\s+instructions?)",
            re.IGNORECASE,
        ),
        "Attempt to extract system prompt",
    ),
    (
        "prompt_extraction",
        re.compile(
            r"(?:repeat|recite|quote)\s+(?:everything|all|the\s+text)\s+"
            r"(?:above|before|from\s+the\s+start)",
            re.IGNORECASE,
        ),
        "Attempt to extract prior context",
    ),
    # Category 4: Code/Command Injection
    (
        "code_injection",
        re.compile(
            r"(?:import\s+os|subprocess\.\w+|eval\s*\(|exec\s*\(|"
            r"__\w+__|os\.system|curl\s+|wget\s+|"
            r"<script|javascript:|onclick=|SELECT\s+.+\s+FROM\s+|"
            r"DROP\s+TABLE|INSERT\s+INTO|UPDATE\s+.+\s+SET)",
            re.IGNORECASE,
        ),
        "Code or command injection attempt",
    ),
    # Category 5: Jailbreak Phrases
    (
        "jailbreak",
        re.compile(
            r"(?:DAN\s+mode|developer\s+mode|unrestricted\s+mode|"
            r"god\s+mode|sudo\s+mode|admin\s+mode|"
            r"jailbreak|no\s+restrictions?|without\s+(?:any\s+)?restrictions?|"
            r"enable\s+(?:all|full)\s+access)",
            re.IGNORECASE,
        ),
        "Known jailbreak technique",
    ),
    # Category 6: Output Format Manipulation
    (
        "format_manipulation",
        re.compile(
            r"(?:respond\s+(?:only\s+)?(?:with|in)|output\s+(?:only|in)|"
            r"format\s+(?:your\s+)?(?:response|output|answer)\s+(?:as|in))\s+"
            r"(?:python|html|markdown|xml|csv|base64|hex|binary|code)",
            re.IGNORECASE,
        ),
        "Attempt to change output format",
    ),
]


@dataclass
class GuardrailResult:
    """Result of input guardrail scan.

    Attributes:
        is_safe:    True if no injection patterns detected
        violations: List of (category, description) tuples for detected patterns
        risk_score: 0.0 (clean) to 1.0 (highly suspicious)
    """

    is_safe: bool = True
    violations: list[tuple[str, str]] = field(default_factory=list)
    risk_score: float = 0.0


def scan_input(sentence: str) -> GuardrailResult:
    """Scan user input for prompt injection patterns.

    This is a fast, regex-based scanner (<1ms) that runs before LLM calls.
    It operates in WARN-ONLY mode: violations are logged but requests are
    NOT blocked, to avoid false positives on legitimate language learning
    sentences that happen to contain trigger words.

    Args:
        sentence: The raw user input sentence to scan

    Returns:
        GuardrailResult with detected violations (if any)
    """
    violations: list[tuple[str, str]] = []

    for category, pattern, description in _INJECTION_PATTERNS:
        if pattern.search(sentence):
            violations.append((category, description))

    if violations:
        risk_score = min(1.0, len(violations) * 0.3)
        unique_categories = {v[0] for v in violations}

        logger.warning(
            "GUARDRAIL_ALERT: Potential prompt injection detected | "
            "risk_score=%.1f | categories=%s | violations=%d | "
            "sentence_preview='%.80s...'",
            risk_score,
            ",".join(sorted(unique_categories)),
            len(violations),
            sentence,
        )

        return GuardrailResult(
            is_safe=False,
            violations=violations,
            risk_score=risk_score,
        )

    return GuardrailResult(is_safe=True, violations=[], risk_score=0.0)
