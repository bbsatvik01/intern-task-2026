"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatMessage,
  ClientMessage,
  ConnectionStatus,
  FeedbackCard,
  LunaState,
  ServerMessage,
  SessionConfig,
  TranscriptWord,
} from "@/lib/types";
import { sounds } from "@/lib/sounds";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:9090/ws/voice-tutor";

export function useVoiceTutor() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [lunaState, setLunaState] = useState<LunaState>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [feedbacks, setFeedbacks] = useState<FeedbackCard[]>([]);
  const [isActive, setIsActive] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const currentUserMsgRef = useRef<string | null>(null);
  const currentTutorMsgRef = useRef<string | null>(null);
  const tutorWordIndexRef = useRef<number>(0);
  const happyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Callbacks for external consumers ----
  const onFeedbackRef = useRef<((fb: FeedbackCard) => void) | null>(null);

  const setOnFeedback = useCallback((cb: (fb: FeedbackCard) => void) => {
    onFeedbackRef.current = cb;
  }, []);

  // ---- WebSocket message handler ----
  const handleMessage = useCallback((event: MessageEvent) => {
    if (event.data instanceof ArrayBuffer) {
      // Binary = PCM audio from tutor
      if (!playbackNodeRef.current) return;
      if (playbackCtxRef.current?.state === "suspended") playbackCtxRef.current.resume();
      const int16 = new Int16Array(event.data);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
      playbackNodeRef.current.port.postMessage({ type: "audio", samples: float32 });
      setLunaState("speaking");
      return;
    }

    const msg: ServerMessage = JSON.parse(event.data);

    switch (msg.type) {
      case "session_ready":
        setStatus("connected");
        setSessionId(msg.session_id || null);
        setLunaState("listening");
        sounds.sessionStart();
        break;

      case "transcription":
        if (msg.transcription) {
          const { role, text } = msg.transcription;
          if (role === "user") {
            if (!currentUserMsgRef.current) {
              const id = Date.now().toString(36);
              currentUserMsgRef.current = id;
              setMessages((prev) => [...prev, { id, role: "user", text, timestamp: Date.now() }]);
            } else {
              setMessages((prev) =>
                prev.map((m) => (m.id === currentUserMsgRef.current ? { ...m, text } : m))
              );
            }
            setLunaState("listening");
          } else {
            // Tutor transcription: track each chunk as a word for karaoke highlighting
            const now = Date.now();
            const newWord: TranscriptWord = {
              text,
              index: tutorWordIndexRef.current++,
              receivedAt: now,
            };

            if (!currentTutorMsgRef.current) {
              const id = Date.now().toString(36);
              currentTutorMsgRef.current = id;
              tutorWordIndexRef.current = 1; // reset for new message
              newWord.index = 0;
              setMessages((prev) => [...prev, {
                id, role: "tutor", text, timestamp: now,
                words: [newWord], activeWordIndex: 0, isStreaming: true,
              }]);
            } else {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== currentTutorMsgRef.current) return m;
                  const words = [...(m.words || []), newWord];
                  const fullText = words.map((w) => w.text).join(" ");
                  return { ...m, text: fullText, words, activeWordIndex: newWord.index, isStreaming: true };
                })
              );
            }
          }
        }
        break;

      case "feedback":
        if (msg.feedback) {
          setFeedbacks((prev) => [msg.feedback!, ...prev]);
          sounds.feedbackCard();
          if (msg.feedback.is_correct) {
            sounds.correctAnswer();
            triggerHappy();
          } else {
            sounds.errorFound();
          }
          onFeedbackRef.current?.(msg.feedback);
        }
        break;

      case "turn_end":
        // Finalize: mark streaming done, clear active word highlight
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentTutorMsgRef.current
              ? { ...m, isStreaming: false, activeWordIndex: undefined }
              : m
          )
        );
        currentUserMsgRef.current = null;
        currentTutorMsgRef.current = null;
        tutorWordIndexRef.current = 0;
        setLunaState("listening");
        break;

      case "interrupted":
        playbackNodeRef.current?.port.postMessage({ type: "clear" });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentTutorMsgRef.current
              ? { ...m, isStreaming: false, activeWordIndex: undefined }
              : m
          )
        );
        currentUserMsgRef.current = null;
        currentTutorMsgRef.current = null;
        tutorWordIndexRef.current = 0;
        setLunaState("listening");
        break;

      case "session_resuming":
        setStatus("connecting");
        setLunaState("thinking");
        break;

      case "session_ended":
        cleanup();
        break;

      case "error":
        console.error("Server error:", msg.error);
        setStatus("error");
        setLunaState("idle");
        break;
    }
  }, []);

  function triggerHappy() {
    if (happyTimeoutRef.current) clearTimeout(happyTimeoutRef.current);
    setLunaState("happy");
    happyTimeoutRef.current = setTimeout(() => setLunaState("listening"), 2000);
  }

  // ---- Start session ----
  const startSession = useCallback(async (config: SessionConfig) => {
    try {
      setStatus("connecting");
      setLunaState("thinking");

      // 1. Init playback
      const playCtx = new AudioContext({ sampleRate: 24000 });
      await playCtx.audioWorklet.addModule("/worklets/playback-processor.js");
      const playNode = new AudioWorkletNode(playCtx, "playback-processor");
      playNode.connect(playCtx.destination);
      playbackCtxRef.current = playCtx;
      playbackNodeRef.current = playNode;

      // 2. Init capture
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const capCtx = new AudioContext({ sampleRate: 16000 });
      await capCtx.audioWorklet.addModule("/worklets/capture-processor.js");
      const source = capCtx.createMediaStreamSource(stream);
      const capNode = new AudioWorkletNode(capCtx, "capture-processor");
      source.connect(capNode);
      captureCtxRef.current = capCtx;
      workletNodeRef.current = capNode;

      // 3. Connect WS
      const ws = new WebSocket(WS_URL);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onmessage = handleMessage;
      ws.onerror = () => setStatus("error");
      ws.onclose = () => {
        if (isActive) setStatus("disconnected");
      };

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        setTimeout(() => reject(new Error("WS timeout")), 10000);
      });

      // 4. Send session_start
      const startMsg: ClientMessage = { type: "session_start", config };
      ws.send(JSON.stringify(startMsg));

      // 5. Forward mic audio
      capNode.port.onmessage = (e: MessageEvent) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer);
      };

      setIsActive(true);
    } catch (err) {
      console.error("Failed to start:", err);
      setStatus("error");
      setLunaState("idle");
      cleanup();
    }
  }, [handleMessage]);

  // ---- Stop session ----
  const stopSession = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "session_end" }));
    }
    sounds.sessionEnd();
    cleanup();
  }, []);

  function cleanup() {
    setIsActive(false);
    setStatus("disconnected");
    setLunaState("idle");
    setSessionId(null);
    currentUserMsgRef.current = null;
    currentTutorMsgRef.current = null;

    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    captureCtxRef.current?.close().catch(() => {});
    captureCtxRef.current = null;
    playbackNodeRef.current?.disconnect();
    playbackNodeRef.current = null;
    playbackCtxRef.current?.close().catch(() => {});
    playbackCtxRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
  }

  // ---- Start a text-only session (no mic required) ----
  const ensureTextSession = useCallback(async (config: SessionConfig) => {
    // Already connected — nothing to do
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      setStatus("connecting");
      setLunaState("thinking");

      // Init playback only (so Luna can speak back)
      const playCtx = new AudioContext({ sampleRate: 24000 });
      await playCtx.audioWorklet.addModule("/worklets/playback-processor.js");
      const playNode = new AudioWorkletNode(playCtx, "playback-processor");
      playNode.connect(playCtx.destination);
      playbackCtxRef.current = playCtx;
      playbackNodeRef.current = playNode;

      // Connect WS
      const ws = new WebSocket(WS_URL);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onmessage = handleMessage;
      ws.onerror = () => setStatus("error");
      ws.onclose = () => setStatus("disconnected");

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        setTimeout(() => reject(new Error("WS timeout")), 10000);
      });

      // Send session_start
      ws.send(JSON.stringify({ type: "session_start", config } as ClientMessage));
      setIsActive(true);
    } catch (err) {
      console.error("Failed to start text session:", err);
      setStatus("error");
      setLunaState("idle");
    }
  }, [handleMessage]);

  // ---- Send text (auto-connects if needed) ----
  const sendText = useCallback((text: string, config?: SessionConfig) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      // Auto-start a text-only session, then send
      if (config) {
        ensureTextSession(config).then(() => {
          // Small delay for session_ready
          setTimeout(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "text_input", data: text }));
            }
          }, 500);
        });
      }
      // Add message to UI immediately
      const id = Date.now().toString(36);
      setMessages((prev) => [...prev, { id, role: "user", text, timestamp: Date.now() }]);
      setLunaState("thinking");
      return;
    }
    wsRef.current.send(JSON.stringify({ type: "text_input", data: text }));
    const id = Date.now().toString(36);
    setMessages((prev) => [...prev, { id, role: "user", text, timestamp: Date.now() }]);
    setLunaState("thinking");
  }, [ensureTextSession]);

  // ---- Send video frame ----
  const sendVideoFrame = useCallback((base64: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "video_frame", data: base64 }));
  }, []);

  // ---- Send topic selection as text instruction ----
  const selectTopic = useCallback((topicId: string, topicLabel: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const instruction = `Let's practice a conversation about: ${topicLabel}. Start the scenario.`;
    wsRef.current.send(JSON.stringify({ type: "text_input", data: instruction }));
    setLunaState("thinking");
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => { cleanup(); };
  }, []);

  // Keepalive ping
  useEffect(() => {
    if (!isActive) return;
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [isActive]);

  return {
    status,
    lunaState,
    messages,
    feedbacks,
    isActive,
    sessionId,
    startSession,
    stopSession,
    sendText,
    sendVideoFrame,
    selectTopic,
    setOnFeedback,
    setLunaState,
  };
}
