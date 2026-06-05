"use client";

import { TOPICS } from "@/lib/types";

export default function TopicsBar({
  visible,
  activeTopic,
  onSelect,
}: {
  visible: boolean;
  activeTopic: string;
  onSelect: (id: string, label: string) => void;
}) {
  if (!visible) return null;

  return (
    <div className="flex items-center gap-2 px-5 py-2 bg-white border-b border-slate-200 overflow-x-auto">
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400 shrink-0">Topics</span>
      {TOPICS.map((t) => (
        <button
          key={t.id}
          onClick={() => onSelect(t.id, t.label)}
          className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
            activeTopic === t.id
              ? "bg-gradient-to-r from-brand to-brand-dark text-white shadow-sm"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          {t.emoji} {t.label}
        </button>
      ))}
    </div>
  );
}
