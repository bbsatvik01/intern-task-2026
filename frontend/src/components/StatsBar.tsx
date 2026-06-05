"use client";

interface StatsBarProps {
  streak: number;
  accuracy: number;
  cefrLevel: string;
  cefrProgress: number;
  flashcardCount: number;
  visible: boolean;
}

export default function StatsBar({ streak, accuracy, cefrLevel, cefrProgress, flashcardCount, visible }: StatsBarProps) {
  if (!visible) return null;

  return (
    <div className="flex items-center gap-4 text-xs">
      {/* Streak */}
      <div className="flex items-center gap-1" title="Correct streak">
        <span>🔥</span>
        <span className={`font-bold tabular-nums ${streak >= 5 ? "text-orange-500" : "text-slate-600"}`}>{streak}</span>
      </div>

      {/* Accuracy */}
      <div className="flex items-center gap-1" title="Accuracy">
        <span>🎯</span>
        <span className="font-bold tabular-nums text-slate-600">{accuracy > 0 ? `${accuracy}%` : "-"}</span>
      </div>

      {/* CEFR Level + Progress */}
      <div className="flex items-center gap-1.5" title="CEFR Level">
        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-extrabold bg-gradient-to-r from-brand to-brand-dark text-white">
          {cefrLevel}
        </span>
        <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand to-brand-dark rounded-full transition-all duration-500"
            style={{ width: `${cefrProgress}%` }}
          />
        </div>
      </div>

      {/* Flashcards */}
      <div className="flex items-center gap-1" title="Flashcards saved">
        <span>📚</span>
        <span className="font-bold tabular-nums text-slate-600">{flashcardCount}</span>
      </div>
    </div>
  );
}
