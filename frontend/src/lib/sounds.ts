/** Programmatic sound effects using Web Audio API — no external files. */

let ctx: AudioContext | null = null;
let enabled = true;

function getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

function tone(freq: number, dur: number, type: OscillatorType = "sine", vol = 0.12) {
  if (!enabled) return;
  const c = getCtx();
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(vol, c.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, c.currentTime + dur);
  osc.connect(gain).connect(c.destination);
  osc.start();
  osc.stop(c.currentTime + dur);
}

export const sounds = {
  sessionStart() { tone(523, 0.15); setTimeout(() => tone(659, 0.25), 120); },
  sessionEnd() { tone(440, 0.3, "sine", 0.06); },
  feedbackCard() {
    if (!enabled) return;
    const c = getCtx();
    const o = c.createOscillator(); const g = c.createGain();
    o.type = "sine";
    o.frequency.setValueAtTime(800, c.currentTime);
    o.frequency.exponentialRampToValueAtTime(400, c.currentTime + 0.08);
    g.gain.setValueAtTime(0.08, c.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, c.currentTime + 0.12);
    o.connect(g).connect(c.destination); o.start(); o.stop(c.currentTime + 0.12);
  },
  correctAnswer() {
    tone(523, 0.12, "sine", 0.08);
    setTimeout(() => tone(659, 0.12, "sine", 0.08), 80);
    setTimeout(() => tone(784, 0.25, "sine", 0.1), 160);
  },
  errorFound() { tone(330, 0.2, "triangle", 0.05); },
  streakMilestone() {
    tone(523, 0.1, "sine", 0.08);
    setTimeout(() => tone(659, 0.1, "sine", 0.08), 100);
    setTimeout(() => tone(784, 0.1, "sine", 0.08), 200);
    setTimeout(() => tone(1047, 0.35, "sine", 0.12), 300);
  },
  flashcardSaved() { tone(880, 0.15, "sine", 0.06); },
  toggle() { enabled = !enabled; return enabled; },
  get enabled() { return enabled; },
};
