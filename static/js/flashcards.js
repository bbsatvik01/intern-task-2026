/**
 * Vocabulary flashcard system.
 * Stores words learned during sessions with translations and context.
 * Persists to localStorage for cross-session retention.
 */
class FlashcardManager {
  constructor() {
    this._storageKey = 'pangea_flashcards';
    this.cards = this._load();
  }

  /** Add a new flashcard from a correction or vocabulary teaching. */
  add(word, translation, context, language, errorType) {
    // Deduplicate by word+language
    const existing = this.cards.find(
      c => c.word.toLowerCase() === word.toLowerCase() && c.language === language
    );
    if (existing) {
      existing.reviewCount = (existing.reviewCount || 0);
      existing.lastSeen = Date.now();
      this._save();
      return false; // already exists
    }

    this.cards.unshift({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      word,
      translation,
      context,
      language,
      errorType: errorType || null,
      createdAt: Date.now(),
      lastSeen: Date.now(),
      reviewCount: 0,
      mastered: false,
    });

    this._save();
    return true; // new card
  }

  /** Add flashcards from a feedback response. */
  addFromFeedback(feedback, targetLang, nativeLang) {
    const added = [];
    for (const err of (feedback.errors || [])) {
      if (err.correction && err.original) {
        const wasNew = this.add(
          err.correction,
          err.explanation,
          `${err.original} → ${err.correction}`,
          targetLang,
          err.error_type,
        );
        if (wasNew) added.push(err.correction);
      }
    }
    return added;
  }

  /** Get cards for review (least recently seen first). */
  getForReview(limit = 10) {
    return [...this.cards]
      .filter(c => !c.mastered)
      .sort((a, b) => a.lastSeen - b.lastSeen)
      .slice(0, limit);
  }

  /** Mark a card as reviewed. */
  markReviewed(cardId, correct) {
    const card = this.cards.find(c => c.id === cardId);
    if (card) {
      card.lastSeen = Date.now();
      card.reviewCount++;
      if (correct && card.reviewCount >= 5) {
        card.mastered = true;
      }
      this._save();
    }
  }

  get count() { return this.cards.length; }
  get masteredCount() { return this.cards.filter(c => c.mastered).length; }

  _load() {
    try {
      return JSON.parse(localStorage.getItem(this._storageKey) || '[]');
    } catch {
      return [];
    }
  }

  _save() {
    try {
      localStorage.setItem(this._storageKey, JSON.stringify(this.cards));
    } catch { /* quota exceeded — silently fail */ }
  }
}
