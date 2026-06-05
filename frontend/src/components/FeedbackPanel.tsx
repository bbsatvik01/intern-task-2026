"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { FeedbackCard, FeedbackError, Flashcard, LunaState } from "@/lib/types";

/** Make words in text clickable — wraps each word in a button. */
function ClickableText({
  text,
  onWordClick,
  className,
}: {
  text: string;
  onWordClick: (word: string) => void;
  className?: string;
}) {
  const words = text.split(/(\s+)/);
  return (
    <span className={className}>
      {words.map((w, i) =>
        w.trim() ? (
          <button
            key={i}
            onClick={() => onWordClick(w)}
            className="hover:bg-brand-light hover:text-brand-dark rounded px-0.5 -mx-0.5 transition-colors cursor-pointer"
            title={`Ask Luna about "${w}"`}
          >
            {w}
          </button>
        ) : (
          <span key={i}>{w}</span>
        )
      )}
    </span>
  );
}

function FeedbackCardItem({
  fb,
  index,
  isHighlighted,
  onWordClick,
  onErrorClick,
}: {
  fb: FeedbackCard;
  index: number;
  isHighlighted: boolean;
  onWordClick: (word: string, context: string) => void;
  onErrorClick: (err: FeedbackError) => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20, scale: 0.95 }}
      animate={{
        opacity: 1,
        x: 0,
        scale: 1,
        boxShadow: isHighlighted
          ? "0 0 0 2px #8560E0, 0 0 20px rgba(133,96,224,0.15)"
          : "0 1px 2px rgba(0,0,0,0.04)",
      }}
      transition={{ duration: 0.35, delay: 0.05 }}
      className={`rounded-2xl p-3.5 border bg-white transition-all ${
        fb.is_correct
          ? "border-green-400 border-l-4 bg-green-50/50"
          : "border-slate-200 border-l-4 border-l-brand"
      }`}
    >
      <div className="flex justify-between items-center mb-2">
        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-brand-light text-brand-dark">
          {fb.difficulty}
        </span>
        <span className={`text-xs font-bold ${fb.is_correct ? "text-green-500" : "text-red-500"}`}>
          {fb.is_correct ? "✓ Correct!" : `${fb.errors.length} error(s)`}
        </span>
      </div>

      {!fb.is_correct && (
        <div className="text-sm text-slate-600 italic px-3 py-2 bg-slate-50 rounded-lg border-l-3 border-brand mb-2">
          <ClickableText
            text={fb.corrected_sentence}
            onWordClick={(w) => onWordClick(w, fb.corrected_sentence)}
          />
        </div>
      )}

      {fb.errors.map((err, i) => (
        <motion.div
          key={i}
          className={`py-2 ${i > 0 ? "border-t border-slate-100" : ""} group cursor-pointer rounded-lg px-1 -mx-1 hover:bg-brand-light/30 transition-colors`}
          onClick={() => onErrorClick(err)}
          whileTap={{ scale: 0.98 }}
          title={`Tap to ask Luna about this correction`}
        >
          <div className="flex items-center gap-1.5 flex-wrap text-sm">
            <span className="line-through text-red-500 font-semibold">{err.original}</span>
            <motion.span
              className="text-slate-300"
              animate={{ x: [0, 3, 0] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              →
            </motion.span>
            <span className="text-green-600 font-bold">{err.correction}</span>
            <span className={`px-1.5 py-px rounded-full text-[9px] font-bold uppercase tracking-wide ${errorTypeStyle(err.error_type)}`}>
              {err.error_type.replace("_", " ")}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            <ClickableText text={err.explanation} onWordClick={(w) => onWordClick(w, err.explanation)} />
          </p>
          <p className="text-[10px] text-brand opacity-0 group-hover:opacity-100 transition-opacity mt-1 font-medium">
            ↗ Tap to discuss with Luna
          </p>
        </motion.div>
      ))}
    </motion.div>
  );
}

function FlashcardItem({ card, onWordClick }: { card: Flashcard; onWordClick: (word: string) => void }) {
  const [flipped, setFlipped] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="rounded-2xl border border-slate-200 bg-white overflow-hidden cursor-pointer"
      onClick={() => setFlipped(!flipped)}
      whileTap={{ scale: 0.98 }}
    >
      <div className="p-3">
        <div className="flex justify-between items-center mb-1">
          <button
            onClick={(e) => { e.stopPropagation(); onWordClick(card.word); }}
            className="text-sm font-bold text-brand-dark hover:underline"
            title={`Ask Luna about "${card.word}"`}
          >
            {card.word}
          </button>
          <div className="flex items-center gap-1">
            {card.mastered && (
              <span className="text-[10px] font-bold text-green-500 bg-green-50 px-2 py-0.5 rounded-full">Mastered</span>
            )}
            <span className="text-[10px] text-slate-300">{flipped ? "▲" : "▼"}</span>
          </div>
        </div>
        <p className="text-xs text-slate-500">{card.context}</p>
        <AnimatePresence>
          {flipped && (
            <motion.p
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="text-xs text-slate-400 mt-1 overflow-hidden"
            >
              {card.translation}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function errorTypeStyle(type: string): string {
  const map: Record<string, string> = {
    grammar: "bg-purple-50 text-purple-700",
    conjugation: "bg-blue-50 text-blue-700",
    spelling: "bg-orange-50 text-orange-700",
    word_choice: "bg-green-50 text-green-700",
    word_order: "bg-purple-50 text-purple-700",
    missing_word: "bg-purple-50 text-purple-700",
    extra_word: "bg-purple-50 text-purple-700",
    gender_agreement: "bg-blue-50 text-blue-700",
    number_agreement: "bg-blue-50 text-blue-700",
    tone_register: "bg-green-50 text-green-700",
    punctuation: "bg-slate-100 text-slate-600",
  };
  return map[type] || "bg-slate-100 text-slate-500";
}

export default function FeedbackPanel({
  feedbacks,
  flashcards,
  lunaState,
  onAskAboutWord,
  onAskAboutError,
}: {
  feedbacks: FeedbackCard[];
  flashcards: Flashcard[];
  lunaState: LunaState;
  onAskAboutWord: (word: string, context: string) => void;
  onAskAboutError: (err: FeedbackError) => void;
}) {
  const [tab, setTab] = useState<"corrections" | "flashcards">("corrections");

  // Highlight the newest card when Luna is speaking about a correction
  const highlightIdx = lunaState === "speaking" && feedbacks.length > 0 ? 0 : -1;

  return (
    <aside className="w-80 min-w-[280px] bg-white border-l border-slate-200 flex flex-col">
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setTab("corrections")}
          className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-wide text-center transition ${
            tab === "corrections" ? "text-brand-dark border-b-2 border-brand" : "text-slate-400 hover:text-slate-600"
          }`}
        >
          Corrections
          {feedbacks.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-brand-light text-brand-dark text-[10px]">{feedbacks.length}</span>
          )}
        </button>
        <button
          onClick={() => setTab("flashcards")}
          className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-wide text-center transition ${
            tab === "flashcards" ? "text-brand-dark border-b-2 border-brand" : "text-slate-400 hover:text-slate-600"
          }`}
        >
          Flashcards
          {flashcards.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-brand-light text-brand-dark text-[10px]">{flashcards.length}</span>
          )}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5 custom-scrollbar">
        {tab === "corrections" && (
          <>
            {feedbacks.length === 0 && (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-xs text-center gap-2 px-4">
                <svg width={36} height={36} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="text-slate-300">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <p>Grammar corrections appear here as you speak.</p>
              </div>
            )}
            <AnimatePresence>
              {feedbacks.map((fb, i) => (
                <FeedbackCardItem
                  key={i}
                  fb={fb}
                  index={i}
                  isHighlighted={i === highlightIdx}
                  onWordClick={onAskAboutWord}
                  onErrorClick={onAskAboutError}
                />
              ))}
            </AnimatePresence>
          </>
        )}

        {tab === "flashcards" && (
          <>
            {flashcards.length === 0 && (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-xs text-center gap-2 px-4">
                <p>Words from corrections are saved as flashcards automatically.</p>
              </div>
            )}
            <AnimatePresence>
              {flashcards.map((card) => (
                <FlashcardItem
                  key={card.id}
                  card={card}
                  onWordClick={(w) => onAskAboutWord(w, "")}
                />
              ))}
            </AnimatePresence>
          </>
        )}
      </div>
    </aside>
  );
}
