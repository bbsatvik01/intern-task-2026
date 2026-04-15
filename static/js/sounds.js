/**
 * Sound effects system using Web Audio API.
 * Generates all sounds programmatically — no external audio files needed.
 */
class SoundEffects {
  constructor() {
    this._ctx = null;
    this._enabled = true;
  }

  _getCtx() {
    if (!this._ctx) {
      this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this._ctx.state === 'suspended') {
      this._ctx.resume();
    }
    return this._ctx;
  }

  _playTone(freq, duration, type = 'sine', volume = 0.15, ramp = true) {
    if (!this._enabled) return;
    const ctx = this._getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = volume;
    if (ramp) {
      gain.gain.setValueAtTime(volume, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    }
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  }

  /** Session connected — ascending two-note chime */
  sessionStart() {
    if (!this._enabled) return;
    this._playTone(523.25, 0.15, 'sine', 0.12); // C5
    setTimeout(() => this._playTone(659.25, 0.25, 'sine', 0.12), 120); // E5
  }

  /** Session ended — descending note */
  sessionEnd() {
    this._playTone(440, 0.3, 'sine', 0.08);
  }

  /** Feedback card appeared — soft pop */
  feedbackCard() {
    if (!this._enabled) return;
    const ctx = this._getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(800, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.1, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.12);
  }

  /** Correct answer — bright ascending arpeggio */
  correctAnswer() {
    if (!this._enabled) return;
    this._playTone(523.25, 0.12, 'sine', 0.1);     // C5
    setTimeout(() => this._playTone(659.25, 0.12, 'sine', 0.1), 80);  // E5
    setTimeout(() => this._playTone(783.99, 0.25, 'sine', 0.12), 160); // G5
  }

  /** Error found — gentle low note */
  errorFound() {
    this._playTone(330, 0.2, 'triangle', 0.06);
  }

  /** Streak milestone — celebratory fanfare */
  streakMilestone() {
    if (!this._enabled) return;
    this._playTone(523.25, 0.1, 'sine', 0.1);  // C5
    setTimeout(() => this._playTone(659.25, 0.1, 'sine', 0.1), 100);  // E5
    setTimeout(() => this._playTone(783.99, 0.1, 'sine', 0.1), 200);  // G5
    setTimeout(() => this._playTone(1046.5, 0.35, 'sine', 0.14), 300); // C6
  }

  /** Flashcard saved — soft ding */
  flashcardSaved() {
    this._playTone(880, 0.15, 'sine', 0.08);
  }

  /** Topic selected — click */
  topicSelect() {
    this._playTone(600, 0.05, 'square', 0.04);
  }

  toggle() {
    this._enabled = !this._enabled;
    return this._enabled;
  }

  get enabled() { return this._enabled; }
}
