"""Real-time voice + vision language tutor using Gemini 3.1 Flash Live API.

This module provides:
- GeminiLiveSession: wraps the GenAI SDK live session with audio/video relay,
  function-call dispatch to the existing feedback pipeline, and session management.
- FastAPI WebSocket endpoint at /ws/voice-tutor for browser clients.

Architecture:
  Browser <-> WebSocket <-> GeminiLiveSession <-> Gemini Live API
                                   |
                           analyze_sentence()
                                   |
                           get_feedback()  (existing pipeline)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.feedback import get_feedback
from app.models import FeedbackRequest
from app.voice_config import (
    AUDIO_INPUT_MIME,
    GEMINI_LIVE_MODEL,
    SESSION_TIMEOUT_SECONDS,
    get_default_voice,
    get_language_code,
)
from app.voice_models import (
    ClientMessage,
    FeedbackCard,
    FeedbackError,
    ServerMessage,
    SessionConfig,
    TranscriptionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Load the voice tutor system prompt once at import time
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "voice_tutor_prompt.txt"
VOICE_TUTOR_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Gemini Live Session wrapper
# ---------------------------------------------------------------------------

class GeminiLiveSession:
    """Manages a single Gemini Live API session for one learner."""

    def __init__(self, config: SessionConfig):
        self.config = config
        self.session_id = str(uuid.uuid4())[:12]
        self._session = None
        self._client = None
        self._ctx_manager = None  # async context manager from connect()
        self._connected = False
        self._resumption_handle: Optional[str] = None
        self._created_at = time.time()
        self._tasks: list[asyncio.Task] = []

    async def connect(self) -> None:
        """Establish connection to Gemini Live API."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError(
                "google-genai package not installed. Run: pip install google-genai"
            )

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY environment variable not set")

        self._client = genai.Client(api_key=api_key)

        # Resolve voice
        voice_name = self.config.voice or get_default_voice(self.config.target_language)
        lang_code = get_language_code(self.config.target_language)

        # Build the system instruction with proficiency context
        system_text = (
            f"{VOICE_TUTOR_PROMPT}\n\n"
            f"<session_context>\n"
            f"Target language: {self.config.target_language}\n"
            f"Native language: {self.config.native_language}\n"
            f"Proficiency level: {self.config.proficiency}\n"
            f"Camera enabled: {self.config.enable_camera}\n"
            f"</session_context>"
        )

        # Function declaration for bridging to the existing feedback pipeline
        analyze_sentence_tool = types.FunctionDeclaration(
            name="analyze_sentence",
            description=(
                "Analyze a sentence spoken by the language learner for grammar, "
                "spelling, and other errors. Returns structured feedback with "
                "corrections and explanations in the learner's native language. "
                "Call this whenever the learner says something that may contain "
                "errors, or when they ask you to check their sentence."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sentence": {
                        "type": "string",
                        "description": "The learner's sentence to analyze",
                    },
                    "target_language": {
                        "type": "string",
                        "description": "The language the sentence is written in",
                    },
                    "native_language": {
                        "type": "string",
                        "description": "The learner's native language for explanations",
                    },
                },
                "required": ["sentence", "target_language", "native_language"],
            },
        )

        # Build session config
        # Note: gemini-3.1-flash-live-preview only outputs AUDIO.
        # Use send_realtime_input() for all mid-session input (not send_client_content).
        connect_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                ),
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_text)]
            ),
            tools=[types.Tool(function_declarations=[analyze_sentence_tool])],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )

        # connect() returns an async context manager — enter it manually
        self._ctx_manager = self._client.aio.live.connect(
            model=GEMINI_LIVE_MODEL,
            config=connect_config,
        )
        self._session = await self._ctx_manager.__aenter__()
        self._connected = True
        logger.info("[%s] Gemini Live session connected (voice=%s, lang=%s)",
                     self.session_id, voice_name, lang_code)

    async def disconnect(self) -> None:
        """Close the Gemini session."""
        self._connected = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self._ctx_manager:
            try:
                await self._ctx_manager.__aexit__(None, None, None)
            except Exception:
                pass
            self._ctx_manager = None
            self._session = None
        logger.info("[%s] Gemini Live session disconnected", self.session_id)

    async def send_audio(self, pcm_data: bytes) -> None:
        """Forward raw PCM audio from the client to Gemini."""
        if not self._connected or not self._session:
            return
        try:
            from google.genai import types
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm_data, mime_type=AUDIO_INPUT_MIME)
            )
        except Exception as e:
            logger.warning("[%s] Error sending audio: %s", self.session_id, e)

    async def send_video_frame(self, jpeg_base64: str) -> None:
        """Forward a JPEG camera frame to Gemini."""
        if not self._connected or not self._session:
            return
        try:
            from google.genai import types
            jpeg_bytes = base64.b64decode(jpeg_base64)
            await self._session.send_realtime_input(
                media=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
            )
        except Exception as e:
            logger.warning("[%s] Error sending video frame: %s", self.session_id, e)

    async def send_text(self, text: str) -> None:
        """Send a text message to Gemini (for text-only fallback mode).

        Note: Gemini 3.1 Flash Live requires send_realtime_input for all
        mid-session input (send_client_content is only for initial history).
        """
        if not self._connected or not self._session:
            return
        try:
            await self._session.send_realtime_input(text=text)
        except Exception as e:
            logger.warning("[%s] Error sending text: %s", self.session_id, e)

    async def receive_loop(self, ws: WebSocket) -> None:
        """Main receive loop: read Gemini responses and relay to the client.

        Handles audio chunks, transcriptions, tool calls, turn signals, and
        session resumption updates. Wraps in while-True because the receive()
        generator completes after each model turn.
        """
        from google.genai import types

        while self._connected:
            try:
                async for msg in self._session.receive():
                    if not self._connected:
                        return

                    # Session resumption handle updates
                    if msg.session_resumption_update:
                        update = msg.session_resumption_update
                        if update.resumable and update.new_handle:
                            self._resumption_handle = update.new_handle

                    server_content = msg.server_content
                    if server_content:
                        # Audio output
                        if server_content.model_turn and server_content.model_turn.parts:
                            for part in server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    # Send raw PCM audio as binary frame
                                    try:
                                        await ws.send_bytes(part.inline_data.data)
                                    except Exception:
                                        return

                        # Input transcription (what the user said)
                        if server_content.input_transcription:
                            text = server_content.input_transcription.text
                            if text and text.strip():
                                msg_out = ServerMessage(
                                    type="transcription",
                                    transcription=TranscriptionUpdate(
                                        role="user", text=text.strip()
                                    ),
                                )
                                try:
                                    await ws.send_text(msg_out.model_dump_json())
                                except Exception:
                                    return

                        # Output transcription (what the tutor said)
                        if server_content.output_transcription:
                            text = server_content.output_transcription.text
                            if text and text.strip():
                                msg_out = ServerMessage(
                                    type="transcription",
                                    transcription=TranscriptionUpdate(
                                        role="tutor", text=text.strip()
                                    ),
                                )
                                try:
                                    await ws.send_text(msg_out.model_dump_json())
                                except Exception:
                                    return

                        # Turn complete signal
                        if server_content.turn_complete:
                            msg_out = ServerMessage(type="turn_end")
                            try:
                                await ws.send_text(msg_out.model_dump_json())
                            except Exception:
                                return

                        # Interrupted (barge-in)
                        if server_content.interrupted:
                            msg_out = ServerMessage(type="interrupted")
                            try:
                                await ws.send_text(msg_out.model_dump_json())
                            except Exception:
                                return

                    # Tool calls (function calling)
                    if msg.tool_call:
                        await self._handle_tool_call(msg.tool_call, ws)

            except asyncio.CancelledError:
                return
            except Exception as e:
                if self._connected:
                    logger.warning("[%s] Receive loop error: %s", self.session_id, e)
                    # Brief pause before retrying the receive loop
                    await asyncio.sleep(0.5)
                else:
                    return

    async def _handle_tool_call(self, tool_call, ws: WebSocket) -> None:
        """Dispatch Gemini function calls to the existing feedback pipeline."""
        from google.genai import types

        for fc in tool_call.function_calls:
            if fc.name == "analyze_sentence":
                args = fc.args
                feedback_card = None
                result_dict: dict

                try:
                    # Bridge to existing pipeline
                    request = FeedbackRequest(
                        sentence=args.get("sentence", ""),
                        target_language=args.get(
                            "target_language", self.config.target_language
                        ),
                        native_language=args.get(
                            "native_language", self.config.native_language
                        ),
                    )
                    response = await get_feedback(request)

                    # Build result for Gemini
                    result_dict = response.model_dump()

                    # Build feedback card for frontend display
                    feedback_card = FeedbackCard(
                        corrected_sentence=response.corrected_sentence,
                        is_correct=response.is_correct,
                        difficulty=response.difficulty,
                        errors=[
                            FeedbackError(
                                original=err.original,
                                correction=err.correction,
                                error_type=err.error_type,
                                explanation=err.explanation,
                            )
                            for err in response.errors
                        ],
                    )

                except Exception as e:
                    logger.error(
                        "[%s] analyze_sentence failed: %s", self.session_id, e
                    )
                    result_dict = {
                        "error": "Analysis temporarily unavailable",
                        "corrected_sentence": args.get("sentence", ""),
                        "is_correct": True,
                        "errors": [],
                        "difficulty": "A1",
                    }

                # Send function response back to Gemini
                try:
                    await self._session.send_tool_response(
                        function_responses=[
                            types.FunctionResponse(
                                name="analyze_sentence",
                                response=result_dict,
                                id=fc.id,
                            )
                        ]
                    )
                except Exception as e:
                    logger.error(
                        "[%s] Failed to send tool response: %s",
                        self.session_id, e,
                    )

                # Send feedback card to the frontend
                if feedback_card:
                    msg_out = ServerMessage(
                        type="feedback", feedback=feedback_card
                    )
                    try:
                        await ws.send_text(msg_out.model_dump_json())
                    except Exception:
                        pass

    async def check_session_timeout(self, ws: WebSocket) -> None:
        """Background task: proactively resume session before Gemini's 10-min limit."""
        while self._connected:
            await asyncio.sleep(10)
            elapsed = time.time() - self._created_at
            if elapsed >= SESSION_TIMEOUT_SECONDS and self._connected:
                logger.info("[%s] Session timeout — resuming", self.session_id)
                try:
                    # Notify client
                    msg = ServerMessage(type="session_resuming")
                    await ws.send_text(msg.model_dump_json())

                    # Disconnect and reconnect with resumption handle
                    old_handle = self._resumption_handle
                    await self.disconnect()
                    self._resumption_handle = old_handle
                    await self.connect()
                    self._created_at = time.time()

                    # Notify client session is back
                    msg = ServerMessage(
                        type="session_ready", session_id=self.session_id
                    )
                    await ws.send_text(msg.model_dump_json())
                except Exception as e:
                    logger.error("[%s] Session resume failed: %s", self.session_id, e)
                    msg = ServerMessage(
                        type="error", error="Session resume failed. Please reconnect."
                    )
                    try:
                        await ws.send_text(msg.model_dump_json())
                    except Exception:
                        pass
                    return


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/voice-tutor")
async def websocket_voice_tutor(ws: WebSocket):
    """WebSocket endpoint for the real-time voice tutor.

    Protocol:
      1. Client connects, sends a text frame with {"type": "session_start", "config": {...}}
      2. Server connects to Gemini, sends back {"type": "session_ready", "session_id": "..."}
      3. Client streams binary PCM audio frames; server streams back binary PCM + JSON
      4. Client sends {"type": "session_end"} or disconnects to close

    Binary frames = raw PCM audio (no base64 overhead).
    Text frames = JSON control messages.
    """
    await ws.accept()
    session: Optional[GeminiLiveSession] = None

    try:
        # Wait for session_start message
        raw = await asyncio.wait_for(ws.receive_text(), timeout=30)
        try:
            client_msg = ClientMessage.model_validate_json(raw)
        except Exception as e:
            err = ServerMessage(type="error", error=f"Invalid message: {e}")
            await ws.send_text(err.model_dump_json())
            await ws.close()
            return

        if client_msg.type != "session_start" or not client_msg.config:
            err = ServerMessage(
                type="error",
                error="First message must be session_start with config",
            )
            await ws.send_text(err.model_dump_json())
            await ws.close()
            return

        # Create and connect the Gemini session
        session = GeminiLiveSession(client_msg.config)
        try:
            await session.connect()
        except Exception as e:
            logger.error("Gemini connection failed: %s", e)
            err = ServerMessage(type="error", error=str(e))
            await ws.send_text(err.model_dump_json())
            await ws.close()
            return

        # Notify client
        ready = ServerMessage(
            type="session_ready", session_id=session.session_id
        )
        await ws.send_text(ready.model_dump_json())

        # Start background tasks
        receive_task = asyncio.create_task(session.receive_loop(ws))
        timeout_task = asyncio.create_task(session.check_session_timeout(ws))

        # Main loop: receive from client and forward to Gemini
        try:
            while True:
                message = await ws.receive()
                msg_type = message.get("type", "")

                if msg_type == "websocket.disconnect":
                    break

                # Binary frame = PCM audio from microphone
                if "bytes" in message and message["bytes"]:
                    await session.send_audio(message["bytes"])

                # Text frame = JSON control message
                elif "text" in message and message["text"]:
                    try:
                        client_msg = ClientMessage.model_validate_json(
                            message["text"]
                        )
                    except Exception:
                        continue  # Ignore malformed messages

                    if client_msg.type == "session_end":
                        break
                    elif client_msg.type == "video_frame" and client_msg.data:
                        await session.send_video_frame(client_msg.data)
                    elif client_msg.type == "text_input" and client_msg.data:
                        await session.send_text(client_msg.data)
                    elif client_msg.type == "ping":
                        pong = ServerMessage(type="pong")
                        await ws.send_text(pong.model_dump_json())

        except WebSocketDisconnect:
            logger.info("[%s] Client disconnected", session.session_id)
        except asyncio.CancelledError:
            pass
        finally:
            receive_task.cancel()
            timeout_task.cancel()
            try:
                await receive_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await timeout_task
            except (asyncio.CancelledError, Exception):
                pass

    except asyncio.TimeoutError:
        err = ServerMessage(type="error", error="Timed out waiting for session_start")
        try:
            await ws.send_text(err.model_dump_json())
        except Exception:
            pass
    except Exception as e:
        logger.error("Voice tutor WS error: %s", e)
        try:
            err = ServerMessage(type="error", error="Internal server error")
            await ws.send_text(err.model_dump_json())
        except Exception:
            pass
    finally:
        if session:
            await session.disconnect()
            ended = ServerMessage(type="session_ended")
            try:
                await ws.send_text(ended.model_dump_json())
            except Exception:
                pass
        try:
            await ws.close()
        except Exception:
            pass
