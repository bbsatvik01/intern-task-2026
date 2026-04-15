"""Unit tests for the voice tutor backend modules.

These tests run without any API keys and cover:
- voice_config: language/voice mappings
- voice_models: Pydantic model validation
- voice_tutor: WebSocket protocol behavior (mock Gemini)
"""

import json

import pytest

from app.voice_config import (
    AVAILABLE_VOICES,
    DEFAULT_VOICE,
    LANGUAGE_TO_GEMINI_CODE,
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


# =========================================================================
# voice_config tests
# =========================================================================


class TestVoiceConfig:
    """Test language/voice configuration mappings."""

    def test_all_languages_have_valid_bcp47_codes(self):
        for lang, code in LANGUAGE_TO_GEMINI_CODE.items():
            assert isinstance(lang, str)
            assert isinstance(code, str)
            assert "-" in code, f"BCP-47 code should contain dash: {code}"

    def test_get_language_code_known(self):
        assert get_language_code("spanish") == "es-US"
        assert get_language_code("french") == "fr-FR"
        assert get_language_code("japanese") == "ja-JP"

    def test_get_language_code_case_insensitive(self):
        assert get_language_code("SPANISH") == "es-US"
        assert get_language_code("French") == "fr-FR"

    def test_get_language_code_unknown_falls_back(self):
        assert get_language_code("klingon") == "en-US"
        assert get_language_code("") == "en-US"

    def test_get_default_voice_known(self):
        voice = get_default_voice("spanish")
        assert voice in AVAILABLE_VOICES

    def test_get_default_voice_unknown_falls_back(self):
        assert get_default_voice("unknown_lang") == DEFAULT_VOICE

    def test_available_voices_not_empty(self):
        assert len(AVAILABLE_VOICES) > 0


# =========================================================================
# voice_models tests
# =========================================================================


class TestSessionConfig:
    """Test SessionConfig Pydantic model."""

    def test_minimal_config(self):
        cfg = SessionConfig(target_language="spanish", native_language="english")
        assert cfg.proficiency == "intermediate"
        assert cfg.voice == ""
        assert cfg.enable_camera is False

    def test_full_config(self):
        cfg = SessionConfig(
            target_language="french",
            native_language="english",
            voice="Kore",
            proficiency="advanced",
            enable_camera=True,
        )
        assert cfg.voice == "Kore"
        assert cfg.proficiency == "advanced"
        assert cfg.enable_camera is True

    def test_invalid_proficiency_rejected(self):
        with pytest.raises(Exception):
            SessionConfig(
                target_language="x",
                native_language="y",
                proficiency="expert",
            )


class TestClientMessage:
    """Test ClientMessage Pydantic model."""

    def test_session_start(self):
        msg = ClientMessage(
            type="session_start",
            config=SessionConfig(target_language="spanish", native_language="english"),
        )
        assert msg.type == "session_start"
        assert msg.config.target_language == "spanish"

    def test_session_end(self):
        msg = ClientMessage(type="session_end")
        assert msg.type == "session_end"

    def test_video_frame(self):
        msg = ClientMessage(type="video_frame", data="base64data==")
        assert msg.data == "base64data=="

    def test_text_input(self):
        msg = ClientMessage(type="text_input", data="Hello")
        assert msg.data == "Hello"

    def test_invalid_type_rejected(self):
        with pytest.raises(Exception):
            ClientMessage(type="invalid_type")

    def test_from_json(self):
        raw = '{"type": "session_start", "config": {"target_language": "german", "native_language": "english"}}'
        msg = ClientMessage.model_validate_json(raw)
        assert msg.config.target_language == "german"


class TestServerMessage:
    """Test ServerMessage Pydantic model."""

    def test_session_ready(self):
        msg = ServerMessage(type="session_ready", session_id="abc123")
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "session_ready"
        assert data["session_id"] == "abc123"

    def test_transcription(self):
        msg = ServerMessage(
            type="transcription",
            transcription=TranscriptionUpdate(role="user", text="Hola mundo"),
        )
        data = json.loads(msg.model_dump_json())
        assert data["transcription"]["role"] == "user"
        assert data["transcription"]["text"] == "Hola mundo"

    def test_feedback(self):
        msg = ServerMessage(
            type="feedback",
            feedback=FeedbackCard(
                corrected_sentence="Yo fui al mercado ayer.",
                is_correct=False,
                difficulty="A2",
                errors=[
                    FeedbackError(
                        original="soy fue",
                        correction="fui",
                        error_type="conjugation",
                        explanation="You mixed two verb forms",
                    )
                ],
            ),
        )
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "feedback"
        assert len(data["feedback"]["errors"]) == 1
        assert data["feedback"]["errors"][0]["error_type"] == "conjugation"

    def test_error_message(self):
        msg = ServerMessage(type="error", error="Something went wrong")
        data = json.loads(msg.model_dump_json())
        assert data["error"] == "Something went wrong"

    def test_interrupted(self):
        msg = ServerMessage(type="interrupted")
        assert msg.type == "interrupted"


class TestFeedbackCard:
    """Test FeedbackCard model."""

    def test_correct_sentence(self):
        card = FeedbackCard(
            corrected_sentence="This is correct.",
            is_correct=True,
            difficulty="B1",
            errors=[],
        )
        assert card.is_correct is True
        assert len(card.errors) == 0

    def test_with_errors(self):
        card = FeedbackCard(
            corrected_sentence="Fixed sentence.",
            is_correct=False,
            difficulty="A2",
            errors=[
                FeedbackError(
                    original="bad", correction="good",
                    error_type="grammar", explanation="explanation"
                ),
                FeedbackError(
                    original="wrong", correction="right",
                    error_type="spelling", explanation="spelling fix"
                ),
            ],
        )
        assert len(card.errors) == 2


# =========================================================================
# WebSocket endpoint tests (using FastAPI TestClient)
# =========================================================================


class TestVoiceTutorWebSocket:
    """Test the WebSocket endpoint protocol handling."""

    def test_websocket_connect_and_invalid_first_message(self, client):
        """Sending an invalid first message should return an error."""
        with client.websocket_connect("/ws/voice-tutor") as ws:
            ws.send_text('{"type": "ping"}')
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "session_start" in response["error"]

    def test_websocket_connect_malformed_json(self, client):
        """Sending malformed JSON should return an error."""
        with client.websocket_connect("/ws/voice-tutor") as ws:
            ws.send_text("not json at all")
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_websocket_session_start_without_google_key(self, client, monkeypatch):
        """Starting a session without GOOGLE_API_KEY should return an error."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with client.websocket_connect("/ws/voice-tutor") as ws:
            ws.send_text(json.dumps({
                "type": "session_start",
                "config": {
                    "target_language": "spanish",
                    "native_language": "english",
                },
            }))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
