"""Voice tutor configuration: language codes, voice mappings, Gemini constants."""

# Gemini Live API model
GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"

# Session timing
SESSION_TIMEOUT_SECONDS = 540  # 9 min (buffer under 10-min Gemini limit)

# Audio formats
AUDIO_INPUT_MIME = "audio/pcm;rate=16000"
AUDIO_INPUT_SAMPLE_RATE = 16000
AUDIO_OUTPUT_SAMPLE_RATE = 24000

# Language name -> BCP-47 code for Gemini Live API
LANGUAGE_TO_GEMINI_CODE: dict[str, str] = {
    "arabic": "ar-EG",
    "bengali": "bn-BD",
    "chinese": "zh-CN",
    "dutch": "nl-NL",
    "english": "en-US",
    "french": "fr-FR",
    "german": "de-DE",
    "hindi": "hi-IN",
    "indonesian": "id-ID",
    "italian": "it-IT",
    "japanese": "ja-JP",
    "korean": "ko-KR",
    "marathi": "mr-IN",
    "polish": "pl-PL",
    "portuguese": "pt-BR",
    "romanian": "ro-RO",
    "russian": "ru-RU",
    "spanish": "es-US",
    "tamil": "ta-IN",
    "telugu": "te-IN",
    "thai": "th-TH",
    "turkish": "tr-TR",
    "ukrainian": "uk-UA",
    "vietnamese": "vi-VN",
}

# Available Gemini HD voices
AVAILABLE_VOICES: list[str] = [
    "Aoede", "Charon", "Fenrir", "Kore", "Leda",
    "Orus", "Puck", "Zephyr", "Autonoe", "Enceladus",
    "Iapetus", "Umbriel", "Algieba", "Sadachbia", "Sulafat",
]

# Default voice per language (warm / encouraging tone preferred)
DEFAULT_VOICE_BY_LANGUAGE: dict[str, str] = {
    "english": "Aoede",
    "spanish": "Leda",
    "french": "Kore",
    "german": "Fenrir",
    "japanese": "Zephyr",
    "korean": "Zephyr",
    "portuguese": "Leda",
    "italian": "Kore",
    "chinese": "Zephyr",
    "arabic": "Orus",
    "hindi": "Aoede",
    "russian": "Fenrir",
}

DEFAULT_VOICE = "Aoede"


def get_language_code(language: str) -> str:
    """Resolve a language name to a BCP-47 code. Falls back to en-US."""
    return LANGUAGE_TO_GEMINI_CODE.get(language.lower().strip(), "en-US")


def get_default_voice(language: str) -> str:
    """Get the recommended voice for a given target language."""
    return DEFAULT_VOICE_BY_LANGUAGE.get(language.lower().strip(), DEFAULT_VOICE)
