"""Dual-provider LLM integration with automatic fallback.

Architecture:
- Primary: Anthropic Claude 3.5 Haiku (best multilingual accuracy, natural explanations)
- Fallback: OpenAI GPT-4o-mini (6x cheaper, fast, strong structured output)

Both providers use their SDK's native structured output features:
- Anthropic: messages.create() with JSON mode + Pydantic validation
- OpenAI: chat.completions.parse() with Pydantic response_format

Retry logic uses tenacity with exponential backoff + jitter for resilience
against transient errors (429 rate limits, 500/503 server errors).
"""

import json
import logging
import os
from abc import ABC, abstractmethod

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.models import FeedbackResponse
from app.prompt import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when an LLM provider fails after retries."""

    pass


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> FeedbackResponse:
        """Generate feedback for a learner's sentence."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for logging."""
        ...


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using native JSON mode + Pydantic validation."""

    def __init__(self, model: str = "claude-3-5-haiku-latest"):
        self.model = model
        self._client = None

    @property
    def name(self) -> str:
        return f"Anthropic ({self.model})"

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> FeedbackResponse:
        """Generate feedback using Anthropic Claude with JSON mode."""
        client = self._get_client()
        user_message = build_user_message(sentence, target_language, native_language)

        try:
            message = await client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                temperature=0.1,  # Low temperature for consistent corrections
            )

            # Extract text content from response
            content = message.content[0].text

            # Parse with Pydantic for strict validation
            response = FeedbackResponse.model_validate_json(content)
            logger.info("Anthropic response parsed successfully")
            return response

        except Exception as e:
            logger.error("Anthropic provider error: %s", str(e))
            raise LLMProviderError(f"Anthropic failed: {str(e)}") from e


class OpenAIProvider(LLMProvider):
    """OpenAI provider using chat.completions.parse() with Pydantic structured output."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._client = None

    @property
    def name(self) -> str:
        return f"OpenAI ({self.model})"

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> FeedbackResponse:
        """Generate feedback using OpenAI with structured Pydantic output."""
        client = self._get_client()
        user_message = build_user_message(sentence, target_language, native_language)

        try:
            completion = await client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format=FeedbackResponse,
                temperature=0.1,
            )

            response = completion.choices[0].message.parsed
            if response is None:
                raise LLMProviderError("OpenAI returned null parsed response")

            logger.info("OpenAI response parsed successfully")
            return response

        except Exception as e:
            logger.error("OpenAI provider error: %s", str(e))
            raise LLMProviderError(f"OpenAI failed: {str(e)}") from e


def get_available_providers() -> list[LLMProvider]:
    """Return providers ordered by priority, based on available API keys.

    Priority: Anthropic (best multilingual accuracy) > OpenAI (cost-effective fallback).
    Falls back gracefully to whichever provider(s) have API keys configured.
    """
    providers: list[LLMProvider] = []

    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append(AnthropicProvider())
        logger.info("Anthropic provider available (primary)")

    if os.getenv("OPENAI_API_KEY"):
        providers.append(OpenAIProvider())
        logger.info("OpenAI provider available (%s)", "fallback" if providers else "primary")

    return providers
