"""Pydantic models for the voice tutor WebSocket protocol.

Protocol
--------
Client -> Server:
  Binary frames : raw PCM 16-bit 16 kHz audio chunks (~250 ms each)
  Text frames   : JSON control messages (ClientMessage)

Server -> Client:
  Binary frames : raw PCM 16-bit 24 kHz audio chunks from Gemini
  Text frames   : JSON control messages (ServerMessage)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Client -> Server
# ---------------------------------------------------------------------------

class SessionConfig(BaseModel):
    """Initial configuration sent by the client when starting a session."""

    target_language: str = Field(
        description="Language the learner is practicing, e.g. 'spanish'",
    )
    native_language: str = Field(
        description="Learner's native language for explanations, e.g. 'english'",
    )
    voice: str = Field(
        default="",
        description="Gemini HD voice name (empty = auto-select based on language)",
    )
    proficiency: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate",
    )
    enable_camera: bool = Field(
        default=False,
        description="Whether the client is sending camera frames",
    )


class ClientMessage(BaseModel):
    """JSON control message from the browser client."""

    type: Literal["session_start", "session_end", "video_frame", "text_input", "ping"]
    config: Optional[SessionConfig] = None
    data: Optional[str] = None  # base64 JPEG for video_frame, or text for text_input


# ---------------------------------------------------------------------------
# Server -> Client
# ---------------------------------------------------------------------------

class TranscriptionUpdate(BaseModel):
    """Real-time transcription of user or tutor speech."""

    role: Literal["user", "tutor"]
    text: str
    is_final: bool = False


class FeedbackCard(BaseModel):
    """Structured grammar feedback displayed as a card in the UI."""

    corrected_sentence: str
    is_correct: bool
    difficulty: str
    errors: list[FeedbackError] = Field(default_factory=list)


class FeedbackError(BaseModel):
    """A single error within a FeedbackCard."""

    original: str
    correction: str
    error_type: str
    explanation: str


class ServerMessage(BaseModel):
    """JSON control message from the server to the browser client."""

    type: Literal[
        "session_ready",
        "transcription",
        "feedback",
        "turn_start",
        "turn_end",
        "interrupted",
        "session_resuming",
        "session_ended",
        "error",
        "pong",
    ]
    transcription: Optional[TranscriptionUpdate] = None
    feedback: Optional[FeedbackCard] = None
    error: Optional[str] = None
    session_id: Optional[str] = None


# Fix forward reference – FeedbackCard uses FeedbackError
FeedbackCard.model_rebuild()
