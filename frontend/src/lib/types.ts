/** Shared TypeScript types for the voice tutor. */

export interface SessionConfig {
  target_language: string;
  native_language: string;
  proficiency: "beginner" | "intermediate" | "advanced";
  voice: string;
  enable_camera: boolean;
}

export interface ClientMessage {
  type: "session_start" | "session_end" | "video_frame" | "text_input" | "ping";
  config?: SessionConfig;
  data?: string;
}

export interface TranscriptionUpdate {
  role: "user" | "tutor";
  text: string;
  is_final?: boolean;
}

export interface FeedbackError {
  original: string;
  correction: string;
  error_type: string;
  explanation: string;
}

export interface FeedbackCard {
  corrected_sentence: string;
  is_correct: boolean;
  difficulty: string;
  errors: FeedbackError[];
}

export interface ServerMessage {
  type:
    | "session_ready"
    | "transcription"
    | "feedback"
    | "turn_start"
    | "turn_end"
    | "interrupted"
    | "session_resuming"
    | "session_ended"
    | "error"
    | "pong";
  transcription?: TranscriptionUpdate;
  feedback?: FeedbackCard;
  error?: string;
  session_id?: string;
}

export type LunaState = "idle" | "speaking" | "listening" | "happy" | "thinking";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

/** A single word/chunk in a transcript, with the index it was received at. */
export interface TranscriptWord {
  text: string;
  index: number;       // sequential index within the message
  receivedAt: number;  // timestamp when this chunk arrived
}

export interface ChatMessage {
  id: string;
  role: "user" | "tutor";
  text: string;
  timestamp: number;
  /** For tutor messages: individual transcript words for karaoke highlighting. */
  words?: TranscriptWord[];
  /** Index of the word currently being spoken (for live highlighting). */
  activeWordIndex?: number;
  /** Whether this message is still being streamed. */
  isStreaming?: boolean;
}

export interface Flashcard {
  id: string;
  word: string;
  translation: string;
  context: string;
  language: string;
  errorType: string | null;
  createdAt: number;
  mastered: boolean;
}

export const LANGUAGES = [
  { value: "spanish", label: "Spanish", flag: "🇪🇸" },
  { value: "french", label: "French", flag: "🇫🇷" },
  { value: "german", label: "German", flag: "🇩🇪" },
  { value: "italian", label: "Italian", flag: "🇮🇹" },
  { value: "portuguese", label: "Portuguese", flag: "🇧🇷" },
  { value: "japanese", label: "Japanese", flag: "🇯🇵" },
  { value: "korean", label: "Korean", flag: "🇰🇷" },
  { value: "chinese", label: "Chinese", flag: "🇨🇳" },
  { value: "arabic", label: "Arabic", flag: "🇦🇪" },
  { value: "hindi", label: "Hindi", flag: "🇮🇳" },
  { value: "russian", label: "Russian", flag: "🇷🇺" },
  { value: "turkish", label: "Turkish", flag: "🇹🇷" },
  { value: "dutch", label: "Dutch", flag: "🇳🇱" },
  { value: "thai", label: "Thai", flag: "🇹🇭" },
  { value: "vietnamese", label: "Vietnamese", flag: "🇻🇳" },
  { value: "english", label: "English", flag: "🇬🇧" },
] as const;

export const VOICES = [
  { value: "", label: "Auto" },
  { value: "Aoede", label: "Aoede" },
  { value: "Charon", label: "Charon" },
  { value: "Fenrir", label: "Fenrir" },
  { value: "Kore", label: "Kore" },
  { value: "Leda", label: "Leda" },
  { value: "Puck", label: "Puck" },
  { value: "Zephyr", label: "Zephyr" },
] as const;

export const TOPICS = [
  { id: "free", label: "Free Chat", emoji: "💬" },
  { id: "restaurant", label: "Restaurant", emoji: "🍽️" },
  { id: "directions", label: "Directions", emoji: "🗺️" },
  { id: "shopping", label: "Shopping", emoji: "🛍️" },
  { id: "interview", label: "Job Interview", emoji: "💼" },
  { id: "travel", label: "Travel", emoji: "✈️" },
  { id: "hobbies", label: "Hobbies", emoji: "🎨" },
  { id: "weather", label: "Weather", emoji: "🌤️" },
] as const;
