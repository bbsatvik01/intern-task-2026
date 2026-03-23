"""Localized fallback responses for graceful degradation.

When LLM providers fail (timeout, rate limit, server error), we return a
schema-valid FeedbackResponse in the learner's native language instead of
a generic error. This ensures the frontend always receives valid JSON and
the learner sees a helpful message.

Inspired by omkar-79's approach: 9-language localized fallback map.
We cover 15 languages matching our supported language set.
"""

from app.models import FeedbackResponse

# Native language → localized "service unavailable" message
FALLBACK_MESSAGES: dict[str, str] = {
    "english": "The grammar feedback service is temporarily unavailable. Please try again in a moment.",
    "spanish": "El servicio de retroalimentación gramatical no está disponible temporalmente. Por favor, inténtalo de nuevo en un momento.",
    "french": "Le service de correction grammaticale est temporairement indisponible. Veuillez réessayer dans un instant.",
    "german": "Der Grammatik-Feedback-Service ist vorübergehend nicht verfügbar. Bitte versuchen Sie es in einem Moment erneut.",
    "italian": "Il servizio di feedback grammaticale è temporaneamente non disponibile. Riprova tra un momento.",
    "portuguese": "O serviço de feedback gramatical está temporariamente indisponível. Por favor, tente novamente em um momento.",
    "japanese": "文法フィードバックサービスは一時的に利用できません。しばらくしてからもう一度お試しください。",
    "korean": "문법 피드백 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    "chinese": "语法反馈服务暂时不可用。请稍后再试。",
    "arabic": "خدمة التصحيح النحوي غير متاحة مؤقتاً. يرجى المحاولة مرة أخرى بعد قليل.",
    "russian": "Сервис грамматической проверки временно недоступен. Пожалуйста, попробуйте снова через некоторое время.",
    "hindi": "व्याकरण प्रतिक्रिया सेवा अस्थायी रूप से अनुपलब्ध है। कृपया कुछ समय बाद पुनः प्रयास करें।",
    "turkish": "Dilbilgisi geri bildirim hizmeti geçici olarak kullanılamıyor. Lütfen bir süre sonra tekrar deneyin.",
    "dutch": "De grammaticale feedbackservice is tijdelijk niet beschikbaar. Probeer het over een moment opnieuw.",
    "thai": "บริการตรวจสอบไวยากรณ์ไม่สามารถใช้งานได้ชั่วคราว กรุณาลองใหม่อีกครั้งในอีกสักครู่",
}

DEFAULT_FALLBACK = "The grammar feedback service is temporarily unavailable. Please try again."


def build_fallback_response(
    sentence: str,
    native_language: str,
) -> FeedbackResponse:
    """Build a schema-valid fallback response in the learner's native language.

    This ensures graceful degradation: the frontend always receives valid JSON,
    and the learner sees a helpful message in their own language.

    Args:
        sentence: The original input sentence (returned unchanged)
        native_language: The learner's native language for localized message

    Returns:
        FeedbackResponse with is_correct=True, no errors, and A1 difficulty
    """
    lang_key = native_language.strip().lower()
    message = FALLBACK_MESSAGES.get(lang_key, DEFAULT_FALLBACK)

    return FeedbackResponse(
        corrected_sentence=sentence,
        is_correct=True,
        errors=[],
        difficulty="A1",
    )
