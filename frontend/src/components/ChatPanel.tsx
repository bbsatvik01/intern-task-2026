"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import type { ChatMessage, LunaState, TranscriptWord } from "@/lib/types";

/** Renders tutor words with karaoke-style highlighting on the active word. */
function KaraokeText({
  words,
  activeWordIndex,
  isStreaming,
}: {
  words: TranscriptWord[];
  activeWordIndex?: number;
  isStreaming?: boolean;
}) {
  return (
    <span>
      {words.map((w, i) => {
        const isActive = isStreaming && i === activeWordIndex;
        const isPast = activeWordIndex !== undefined && i < activeWordIndex;
        const isFuture = activeWordIndex !== undefined && i > activeWordIndex;

        return (
          <span key={i}>
            <motion.span
              className={`
                inline rounded-sm px-[2px] -mx-[1px] transition-all duration-150
                ${isActive
                  ? "bg-brand-light text-brand-dark font-bold scale-[1.02]"
                  : isPast
                    ? "text-slate-800"
                    : isFuture
                      ? "text-slate-400"
                      : "text-slate-800"
                }
              `}
              animate={isActive ? { scale: [1, 1.05, 1] } : { scale: 1 }}
              transition={{ duration: 0.2 }}
            >
              {w.text}
            </motion.span>
            {i < words.length - 1 && " "}
          </span>
        );
      })}
      {isStreaming && (
        <motion.span
          className="inline-block w-[6px] h-[14px] bg-brand rounded-full ml-0.5 align-middle"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      )}
    </span>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex items-start gap-2 animate-[bubble-in_0.25s_ease-out]">
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand to-brand-dark flex items-center justify-center text-white text-xs font-bold shrink-0">
        L
      </div>
      <div className="bg-white border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-xs">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="w-2 h-2 bg-brand rounded-full"
              animate={{ scale: [0.6, 1, 0.6], opacity: [0.4, 1, 0.4] }}
              transition={{ duration: 1.4, delay: i * 0.2, repeat: Infinity }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isTutorWithWords = !isUser && msg.words && msg.words.length > 0;

  return (
    <motion.div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
      initial={{ opacity: 0, y: 6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25 }}
    >
      <div
        className={`max-w-[80%] px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-gradient-to-br from-brand to-brand-dark text-white rounded-2xl rounded-br-sm"
            : "bg-white text-slate-900 border border-slate-100 rounded-2xl rounded-bl-sm shadow-xs"
        }`}
      >
        <div className={`text-[10px] font-bold uppercase tracking-wide mb-0.5 ${isUser ? "text-white/60" : "text-brand"}`}>
          {isUser ? "You" : "Luna"}
        </div>

        {isTutorWithWords ? (
          <KaraokeText
            words={msg.words!}
            activeWordIndex={msg.activeWordIndex}
            isStreaming={msg.isStreaming}
          />
        ) : (
          msg.text
        )}
      </div>
    </motion.div>
  );
}

export default function ChatPanel({
  messages,
  lunaState,
  onSendText,
}: {
  messages: ChatMessage[];
  lunaState: LunaState;
  onSendText: (text: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, lunaState]);

  const handleSend = () => {
    const val = inputRef.current?.value.trim();
    if (!val) return;
    onSendText(val);
    if (inputRef.current) inputRef.current.value = "";
  };

  const showThinking = lunaState === "thinking";

  return (
    <section className="flex-1 flex flex-col min-w-0 bg-slate-50">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-2 custom-scrollbar">
        {messages.length === 0 && !showThinking && (
          <div className="flex-1 flex flex-col items-center justify-center text-center text-slate-400 gap-2 px-6">
            <svg width={48} height={48} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="text-slate-300">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <h3 className="text-base font-bold text-slate-500">Talk to Luna</h3>
            <p className="text-sm max-w-xs">Click the mic to start a live voice conversation, or type below.</p>
          </div>
        )}

        {messages.map((m) => (
          <MessageBubble key={m.id} msg={m} />
        ))}

        {showThinking && <ThinkingBubble />}
      </div>

      {/* Text input */}
      <div className="flex gap-2 px-4 py-3 bg-white border-t border-slate-200">
        <input
          ref={inputRef}
          type="text"
          placeholder="Type a message..."
          className="flex-1 px-3.5 py-2 border border-slate-200 rounded-xl text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand-light transition"
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <button
          onClick={handleSend}
          className="p-2 bg-gradient-to-r from-brand to-brand-dark text-white rounded-xl hover:opacity-90 transition"
        >
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <line x1={22} y1={2} x2={11} y2={13} />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </section>
  );
}
