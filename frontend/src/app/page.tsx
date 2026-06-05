"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useVoiceTutor } from "@/hooks/useVoiceTutor";
import Luna from "@/components/Luna";
import ChatPanel from "@/components/ChatPanel";
import FeedbackPanel from "@/components/FeedbackPanel";
import StatsBar from "@/components/StatsBar";
import TopicsBar from "@/components/TopicsBar";
import MilestoneToast from "@/components/MilestoneToast";
import { LANGUAGES, VOICES, type Flashcard, type FeedbackCard, type FeedbackError, type SessionConfig } from "@/lib/types";
import { sounds } from "@/lib/sounds";

const MILESTONES = [3, 5, 10, 25, 50, 100];

export default function VoiceTutorPage() {
  const tutor = useVoiceTutor();

  // Config
  const [targetLang, setTargetLang] = useState("spanish");
  const [nativeLang, setNativeLang] = useState("english");
  const [proficiency, setProficiency] = useState<"beginner" | "intermediate" | "advanced">("intermediate");
  const [voice, setVoice] = useState("");
  const [activeTopic, setActiveTopic] = useState("free");

  // Gamification
  const [streak, setStreak] = useState(0);
  const [bestStreak, setBestStreak] = useState(0);
  const [totalCorrect, setTotalCorrect] = useState(0);
  const [totalAnalyzed, setTotalAnalyzed] = useState(0);
  const [xp, setXp] = useState(0);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [milestoneStreak, setMilestoneStreak] = useState(0);
  const [showMilestone, setShowMilestone] = useState(false);
  const [soundsOn, setSoundsOn] = useState(true);

  // Timer
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // CEFR
  const cefrLevel = xp >= 200 ? "C2" : xp >= 100 ? "C1" : xp >= 50 ? "B2" : xp >= 20 ? "B1" : xp >= 8 ? "A2" : "A1";
  const thresholds = [0, 8, 20, 50, 100, 200, 500];
  const cefrIdx = ["A1", "A2", "B1", "B2", "C1", "C2"].indexOf(cefrLevel);
  const cefrProgress = Math.min(100, Math.round(((xp - thresholds[cefrIdx]) / ((thresholds[cefrIdx + 1] || thresholds[cefrIdx] + 100) - thresholds[cefrIdx])) * 100));
  const accuracy = totalAnalyzed > 0 ? Math.round((totalCorrect / totalAnalyzed) * 100) : 0;

  // Feedback handler for gamification
  const handleFeedback = useCallback((fb: FeedbackCard) => {
    const xpMap: Record<string, number> = { A1: 1, A2: 2, B1: 4, B2: 8, C1: 16, C2: 32 };
    setTotalAnalyzed((p) => p + 1);

    if (fb.is_correct) {
      setTotalCorrect((p) => p + 1);
      setXp((p) => p + (xpMap[fb.difficulty] || 1));
      setStreak((prev) => {
        const next = prev + 1;
        if (next > bestStreak) setBestStreak(next);
        if (MILESTONES.includes(next)) {
          setMilestoneStreak(next);
          setShowMilestone(true);
          sounds.streakMilestone();
        }
        return next;
      });
    } else {
      setStreak(0);
      for (const err of fb.errors) {
        if (err.correction && err.original) {
          setFlashcards((prev) => {
            if (prev.some((c) => c.word === err.correction && c.language === targetLang)) return prev;
            sounds.flashcardSaved();
            return [{
              id: Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
              word: err.correction, translation: err.explanation,
              context: `${err.original} → ${err.correction}`,
              language: targetLang, errorType: err.error_type,
              createdAt: Date.now(), mastered: false,
            }, ...prev];
          });
        }
      }
    }
  }, [targetLang, bestStreak]);

  useEffect(() => { tutor.setOnFeedback(handleFeedback); }, [handleFeedback, tutor.setOnFeedback]);

  // Timer
  useEffect(() => {
    if (tutor.isActive) {
      const start = Date.now();
      timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setElapsed(0);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [tutor.isActive]);

  const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const currentConfig = useCallback((): SessionConfig => ({
    target_language: targetLang, native_language: nativeLang, proficiency, voice, enable_camera: false,
  }), [targetLang, nativeLang, proficiency, voice]);

  const handleMic = () => {
    if (tutor.isActive) { tutor.stopSession(); return; }
    tutor.startSession(currentConfig());
  };

  const handleSendText = useCallback((text: string) => {
    tutor.sendText(text, currentConfig());
  }, [tutor.sendText, currentConfig]);

  const handleTopic = (id: string, label: string) => { setActiveTopic(id); tutor.selectTopic(id, label); };

  const handleAskAboutWord = useCallback((word: string, context: string) => {
    const msg = context
      ? `Can you explain the word "${word}" from this context: "${context.slice(0, 80)}"? Explain it simply.`
      : `Can you explain the word "${word}"? What does it mean and how do I use it?`;
    tutor.sendText(msg, currentConfig());
  }, [tutor.sendText, currentConfig]);

  const handleAskAboutError = useCallback((err: FeedbackError) => {
    tutor.sendText(
      `Explain why "${err.original}" should be "${err.correction}" (${err.error_type}). Give me more examples of this pattern.`,
      currentConfig(),
    );
  }, [tutor.sendText, currentConfig]);

  const tFlag = LANGUAGES.find((l) => l.value === targetLang)?.flag || "";
  const nFlag = LANGUAGES.find((l) => l.value === nativeLang)?.flag || "";

  return (
    <>
      {/* ---- Header ---- */}
      <header className="flex justify-between items-center px-5 py-2.5 bg-white border-b border-slate-200 z-10">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand to-brand-dark flex items-center justify-center text-white text-xs font-extrabold">P</div>
          <span className="text-lg font-extrabold bg-gradient-to-r from-brand to-brand-dark bg-clip-text text-transparent">Pangea</span>
          <span className="text-slate-300 font-light">/</span>
          <span className="text-sm font-medium text-slate-500">Voice Tutor</span>
        </div>
        <StatsBar streak={streak} accuracy={accuracy} cefrLevel={cefrLevel} cefrProgress={cefrProgress} flashcardCount={flashcards.length} visible={tutor.isActive} />
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tabular-nums text-slate-400 w-12 text-center">{fmt(elapsed)}</span>
          <StatusBadge status={tutor.status} />
          <button onClick={() => setSoundsOn(sounds.toggle())} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition" title="Toggle sounds">
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              {soundsOn ? <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" /> : <><line x1={23} y1={9} x2={17} y2={15} /><line x1={17} y1={9} x2={23} y2={15} /></>}
            </svg>
          </button>
        </div>
      </header>

      {/* ---- Config Bar ---- */}
      <div className="flex items-end gap-4 px-5 py-2.5 bg-white border-b border-slate-200 flex-wrap">
        <Cfg label="I'm learning" value={targetLang} onChange={setTargetLang} disabled={tutor.isActive} flag={tFlag}>
          {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.flag} {l.label}</option>)}
        </Cfg>
        <Cfg label="I speak" value={nativeLang} onChange={setNativeLang} disabled={tutor.isActive} flag={nFlag}>
          {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.flag} {l.label}</option>)}
        </Cfg>
        <Cfg label="Level" value={proficiency} onChange={(v) => setProficiency(v as typeof proficiency)} disabled={tutor.isActive}>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </Cfg>
        <Cfg label="Voice" value={voice} onChange={setVoice} disabled={tutor.isActive}>
          {VOICES.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
        </Cfg>
      </div>

      <TopicsBar visible={tutor.isActive} activeTopic={activeTopic} onSelect={handleTopic} />

      {/* ---- Main 3-panel ---- */}
      <main className="flex-1 flex overflow-hidden min-h-0">
        <aside className="w-56 min-w-[220px] bg-white border-r border-slate-200 flex flex-col items-center justify-center p-4">
          <Luna state={tutor.lunaState} />
        </aside>
        <ChatPanel messages={tutor.messages} lunaState={tutor.lunaState} onSendText={handleSendText} />
        <FeedbackPanel
          feedbacks={tutor.feedbacks}
          flashcards={flashcards}
          lunaState={tutor.lunaState}
          onAskAboutWord={handleAskAboutWord}
          onAskAboutError={handleAskAboutError}
        />
      </main>

      <MilestoneToast streak={milestoneStreak} show={showMilestone} onDone={() => setShowMilestone(false)} />

      {/* ---- Mic Button ---- */}
      <footer className="bg-white border-t border-slate-200 py-3 flex justify-center">
        <button onClick={handleMic} className={`relative w-14 h-14 rounded-full flex items-center justify-center text-white transition-all ${tutor.isActive ? "bg-gradient-to-br from-red-500 to-red-600 shadow-[0_4px_14px_rgba(239,68,68,0.4)]" : "bg-gradient-to-br from-brand to-brand-dark shadow-[0_4px_14px_rgba(133,96,224,0.35)] hover:scale-105"}`}>
          {tutor.isActive && <span className="absolute inset-[-4px] rounded-full border-2 border-red-400 animate-[mic-pulse-ring_1.5s_ease-out_infinite]" />}
          {tutor.isActive ? (
            <svg width={24} height={24} viewBox="0 0 24 24" fill="currentColor"><rect x={6} y={6} width={12} height={12} rx={2} /></svg>
          ) : (
            <svg width={24} height={24} viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
            </svg>
          )}
        </button>
      </footer>
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    connected: "bg-green-50 text-green-600",
    connecting: "bg-amber-50 text-amber-700",
    error: "bg-red-50 text-red-600",
    disconnected: "bg-slate-100 text-slate-500",
  };
  const dots: Record<string, string> = {
    connected: "bg-green-500",
    connecting: "bg-amber-500 animate-pulse",
    error: "bg-red-500",
    disconnected: "bg-slate-400",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide ${styles[status] || styles.disconnected}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[status] || dots.disconnected}`} />
      {status}
    </span>
  );
}

function Cfg({ label, value, onChange, disabled, flag, children }: {
  label: string; value: string; onChange: (v: string) => void; disabled?: boolean; flag?: string; children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</label>
      <div className="flex items-center gap-1">
        {flag && <span className="text-base">{flag}</span>}
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}
          className="px-2 py-1 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 bg-white outline-none focus:border-brand focus:ring-2 focus:ring-brand-light disabled:opacity-50 transition">
          {children}
        </select>
      </div>
    </div>
  );
}
