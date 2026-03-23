from __future__ import annotations

"""Dual-provider LLM integration with automatic fallback.

Architecture:
- Primary: OpenAI GPT-4.1 nano (cheapest, fast, strong structured output)
- Fallback: Anthropic Claude Haiku 4.5 (higher quality, natural explanations)

Both providers use their SDK's native structured output features:
- Anthropic: messages.create() with JSON mode + Pydantic validation
- OpenAI: chat.completions.parse() with Pydantic response_format

Retry logic uses tenacity with exponential backoff + jitter for resilience
against TRANSIENT errors only (429 rate limits, 500/503 server errors, timeouts).
Validation errors and auth errors are NOT retried.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.models import FeedbackResponse
from app.prompt import SYSTEM_PROMPT, build_reflexion_message, build_user_message

logger = logging.getLogger(__name__)

# Timeout for individual LLM API calls (seconds).
# With 2 retries + backoff, worst case ≈ 15 + 3 + 15 + 6 + 15 = ~54s total,
# but the first attempt usually succeeds in 2-5s.
LLM_TIMEOUT_SECONDS = 15


class LLMProviderError(Exception):
    """Raised when an LLM provider fails after retries."""

    pass


class TransientLLMError(Exception):
    """Raised for transient errors that should be retried (rate limits, timeouts)."""

    pass


@dataclass
class LLMUsage:
    """Token usage statistics from an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    model: str = ""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Generate feedback for a learner's sentence.

        Returns:
            Tuple of (parsed response, token usage stats)
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for logging."""
        ...

    async def generate_reflexion_feedback(
        self,
        sentence: str,
        target_language: str,
        native_language: str,
        previous_response: FeedbackResponse,
        wrong_indices: list[int],
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Retry with reflexion: feed LLM its own output + specific error feedback.

        Implements Self-Refine (Madaan et al., NeurIPS 2023) for explanation
        language correction. Default implementation calls generate_feedback
        with a reflexion message — subclasses can override for provider-specific
        optimizations.
        """
        # Default: simple retry (subclasses override with reflexion message)
        return await self.generate_feedback(sentence, target_language, native_language)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using native JSON mode + Pydantic validation."""

    def __init__(self, model: str = "claude-haiku-4-5"):
        self.model = model
        self._client = None

    @property
    def name(self) -> str:
        return f"Anthropic ({self.model})"

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=1, max=8, jitter=2),
        retry=retry_if_exception_type(TransientLLMError),
        reraise=True,
    )
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Generate feedback using Anthropic Claude with JSON mode."""
        import anthropic

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

            # Extract text content and parse with Pydantic
            content = message.content[0].text
            response = FeedbackResponse.model_validate_json(content)

            # Track token usage
            usage = LLMUsage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                provider="anthropic",
                model=self.model,
            )
            logger.info(
                "Anthropic response: %d input tokens, %d output tokens",
                usage.input_tokens,
                usage.output_tokens,
            )
            return response, usage

        except (
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        ) as e:
            logger.warning("Anthropic transient error (will retry): %s", str(e))
            raise TransientLLMError(str(e)) from e

        except anthropic.APIStatusError as e:
            logger.error("Anthropic API error (non-retryable): %s", str(e))
            raise LLMProviderError(f"Anthropic API error: {str(e)}") from e

        except Exception as e:
            logger.error("Anthropic provider error: %s", str(e))
            raise LLMProviderError(f"Anthropic failed: {str(e)}") from e

    async def generate_reflexion_feedback(
        self,
        sentence: str,
        target_language: str,
        native_language: str,
        previous_response: FeedbackResponse,
        wrong_indices: list[int],
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Reflexion retry using Anthropic Claude with the previous response as context."""
        import anthropic

        client = self._get_client()
        previous_json = previous_response.model_dump_json(indent=2)
        reflexion_msg = build_reflexion_message(
            sentence, target_language, native_language, previous_json, wrong_indices
        )

        try:
            message = await client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": reflexion_msg}],
                temperature=0.1,
            )
            content = message.content[0].text
            response = FeedbackResponse.model_validate_json(content)
            usage = LLMUsage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                provider="anthropic",
                model=self.model,
            )
            logger.info("Anthropic reflexion: %d in / %d out tokens", usage.input_tokens, usage.output_tokens)
            return response, usage
        except Exception as e:
            logger.warning("Anthropic reflexion failed: %s", str(e))
            raise LLMProviderError(f"Anthropic reflexion failed: {str(e)}") from e


class OpenAIProvider(LLMProvider):
    """OpenAI provider using chat.completions.parse() with Pydantic structured output."""

    def __init__(self, model: str = "gpt-4.1-nano"):
        self.model = model
        self._client = None

    @property
    def name(self) -> str:
        return f"OpenAI ({self.model})"

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai.AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=1, max=8, jitter=2),
        retry=retry_if_exception_type(TransientLLMError),
        reraise=True,
    )
    async def generate_feedback(
        self, sentence: str, target_language: str, native_language: str
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Generate feedback using OpenAI with structured Pydantic output."""
        import openai

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

            # Track token usage
            usage = LLMUsage(
                input_tokens=completion.usage.prompt_tokens if completion.usage else 0,
                output_tokens=completion.usage.completion_tokens if completion.usage else 0,
                provider="openai",
                model=self.model,
            )
            logger.info(
                "OpenAI response: %d input tokens, %d output tokens",
                usage.input_tokens,
                usage.output_tokens,
            )
            return response, usage

        except (openai.APITimeoutError, openai.RateLimitError, openai.APIConnectionError) as e:
            logger.warning("OpenAI transient error (will retry): %s", str(e))
            raise TransientLLMError(str(e)) from e

        except openai.APIStatusError as e:
            logger.error("OpenAI API error (non-retryable): %s", str(e))
            raise LLMProviderError(f"OpenAI API error: {str(e)}") from e

        except Exception as e:
            logger.error("OpenAI provider error: %s", str(e))
            raise LLMProviderError(f"OpenAI failed: {str(e)}") from e

    async def generate_reflexion_feedback(
        self,
        sentence: str,
        target_language: str,
        native_language: str,
        previous_response: FeedbackResponse,
        wrong_indices: list[int],
    ) -> tuple[FeedbackResponse, LLMUsage]:
        """Reflexion retry using OpenAI with the previous response as context."""
        import openai

        client = self._get_client()
        previous_json = previous_response.model_dump_json(indent=2)
        reflexion_msg = build_reflexion_message(
            sentence, target_language, native_language, previous_json, wrong_indices
        )

        try:
            completion = await client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": reflexion_msg},
                ],
                response_format=FeedbackResponse,
                temperature=0.1,
            )
            response = completion.choices[0].message.parsed
            if response is None:
                raise LLMProviderError("OpenAI reflexion returned null parsed response")
            usage = LLMUsage(
                input_tokens=completion.usage.prompt_tokens if completion.usage else 0,
                output_tokens=completion.usage.completion_tokens if completion.usage else 0,
                provider="openai",
                model=self.model,
            )
            logger.info("OpenAI reflexion: %d in / %d out tokens", usage.input_tokens, usage.output_tokens)
            return response, usage
        except Exception as e:
            logger.warning("OpenAI reflexion failed: %s", str(e))
            raise LLMProviderError(f"OpenAI reflexion failed: {str(e)}") from e


def get_available_providers() -> list[LLMProvider]:
    """Return providers ordered by cost-optimized priority.

    Priority: OpenAI GPT-4.1 nano (cheapest at $0.10/1M input) >
              Anthropic Claude Haiku 4.5 (higher quality fallback).
    Falls back gracefully to whichever provider(s) have API keys configured.
    """
    providers: list[LLMProvider] = []

    # Cost-optimized order: cheapest first, quality fallback second
    if os.getenv("OPENAI_API_KEY"):
        providers.append(OpenAIProvider())
        logger.info("OpenAI GPT-4.1 nano provider available (primary — cheapest)")

    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append(AnthropicProvider())
        logger.info(
            "Anthropic Claude Haiku 4.5 provider available (%s)",
            "fallback" if providers else "primary",
        )

    return providers
