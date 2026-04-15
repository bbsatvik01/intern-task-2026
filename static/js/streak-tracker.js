/**
 * Streak tracker — counts consecutive correct sentences and
 * triggers celebrations at milestones (5, 10, 25, 50, 100).
 */
class StreakTracker {
  constructor() {
    this.currentStreak = 0;
    this.bestStreak = 0;
    this.totalCorrect = 0;
    this.totalAnalyzed = 0;
    this.onMilestone = null; // (streak: number) => void
  }

  /** Record a feedback result. Returns true if it's a milestone. */
  record(isCorrect) {
    this.totalAnalyzed++;
    if (isCorrect) {
      this.currentStreak++;
      this.totalCorrect++;
      if (this.currentStreak > this.bestStreak) {
        this.bestStreak = this.currentStreak;
      }
      if (this._isMilestone(this.currentStreak)) {
        this.onMilestone?.(this.currentStreak);
        return true;
      }
    } else {
      this.currentStreak = 0;
    }
    return false;
  }

  _isMilestone(n) {
    return n === 3 || n === 5 || n === 10 || n === 25 || n === 50 || n === 100;
  }

  get accuracy() {
    return this.totalAnalyzed > 0
      ? Math.round((this.totalCorrect / this.totalAnalyzed) * 100)
      : 0;
  }

  reset() {
    this.currentStreak = 0;
    this.totalCorrect = 0;
    this.totalAnalyzed = 0;
  }
}
