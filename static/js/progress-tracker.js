/**
 * CEFR Progress Tracker.
 * Tracks the difficulty distribution of correctly produced sentences
 * and estimates the learner's current CEFR level with a progress bar.
 */
class ProgressTracker {
  constructor() {
    this.levels = { A1: 0, A2: 0, B1: 0, B2: 0, C1: 0, C2: 0 };
    this.totalCorrect = 0;
    this.levelOrder = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
    this.levelXP = { A1: 1, A2: 2, B1: 4, B2: 8, C1: 16, C2: 32 };
    this.xp = 0;
  }

  /** Record a feedback result. */
  record(difficulty, isCorrect) {
    if (!isCorrect) return;
    if (this.levels[difficulty] !== undefined) {
      this.levels[difficulty]++;
      this.xp += this.levelXP[difficulty] || 1;
    }
    this.totalCorrect++;
  }

  /** Estimate the current CEFR level based on XP thresholds. */
  get currentLevel() {
    if (this.xp >= 200) return 'C2';
    if (this.xp >= 100) return 'C1';
    if (this.xp >= 50) return 'B2';
    if (this.xp >= 20) return 'B1';
    if (this.xp >= 8) return 'A2';
    return 'A1';
  }

  /** Get progress within current level as 0-100%. */
  get progressInLevel() {
    const thresholds = [0, 8, 20, 50, 100, 200, 500];
    const idx = this.levelOrder.indexOf(this.currentLevel);
    const low = thresholds[idx];
    const high = thresholds[idx + 1] || thresholds[idx] + 100;
    const progress = ((this.xp - low) / (high - low)) * 100;
    return Math.min(100, Math.max(0, Math.round(progress)));
  }

  /** Get distribution as percentages. */
  get distribution() {
    if (this.totalCorrect === 0) return this.levelOrder.map(l => ({ level: l, pct: 0 }));
    return this.levelOrder.map(l => ({
      level: l,
      pct: Math.round((this.levels[l] / this.totalCorrect) * 100),
    }));
  }

  reset() {
    for (const k of this.levelOrder) this.levels[k] = 0;
    this.totalCorrect = 0;
    this.xp = 0;
  }
}
