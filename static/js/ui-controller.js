/**
 * UI controller: manages DOM updates for conversation bubbles,
 * feedback cards, connection status, Luna avatar states, and video panel.
 */
class UIController {
  constructor() {
    this.conversationEl = document.getElementById('conversation');
    this.feedbackCardsEl = document.getElementById('feedback-cards');
    this.statusBadge = document.getElementById('connection-status');
    this.micButton = document.getElementById('mic-button');
    this.micIcon = document.getElementById('mic-icon');
    this.micIconOff = document.getElementById('mic-icon-off');
    this.timerEl = document.getElementById('session-timer');
    this.cameraPlaceholder = document.getElementById('camera-placeholder');
    this.cameraToggle = document.getElementById('camera-toggle');
    this.lunaAvatar = document.getElementById('luna-avatar');
    this.lunaStateLabel = document.getElementById('luna-state-label');

    this._conversationEmpty = document.getElementById('conversation-empty');
    this._feedbackEmpty = document.getElementById('feedback-empty');
    this._timerInterval = null;
    this._sessionStart = null;
    this._lunaHappyTimeout = null;

    // Accumulate partial transcriptions
    this._currentUserBubble = null;
    this._currentTutorBubble = null;
  }

  // ---- Luna Avatar States ----

  setLunaState(state) {
    // states: idle, speaking, listening, happy, thinking-state
    const avatar = this.lunaAvatar;
    if (!avatar) return;

    // Remove all state classes
    avatar.classList.remove('luna-idle', 'luna-speaking', 'luna-listening', 'luna-happy', 'luna-thinking-state');

    // Add new state
    avatar.classList.add('luna-' + state);

    // Update label
    const labels = {
      'idle': 'Ready to chat',
      'speaking': 'Speaking...',
      'listening': 'Listening...',
      'happy': 'Great job!',
      'thinking-state': 'Thinking...',
    };
    if (this.lunaStateLabel) {
      this.lunaStateLabel.textContent = labels[state] || '';
      this.lunaStateLabel.style.color = state === 'happy' ? '#22c55e' :
                                          state === 'speaking' ? '#6366f1' :
                                          state === 'listening' ? '#0ea5e9' : '';
    }
  }

  triggerHappyReaction() {
    // Show happy state briefly then return to idle
    if (this._lunaHappyTimeout) clearTimeout(this._lunaHappyTimeout);
    this.setLunaState('happy');
    this._lunaHappyTimeout = setTimeout(() => {
      this.setLunaState('idle');
    }, 2000);
  }

  // ---- Connection Status ----

  setStatus(status) {
    const label = status.charAt(0).toUpperCase() + status.slice(1);
    this.statusBadge.innerHTML = `<span class="status-dot"></span>${label}`;
    this.statusBadge.className = 'status-badge status-' + status;
  }

  // ---- Mic Button ----

  setMicActive(active) {
    if (active) {
      this.micButton.classList.add('active');
      this.micIcon.style.display = 'none';
      this.micIconOff.style.display = 'block';
    } else {
      this.micButton.classList.remove('active');
      this.micIcon.style.display = 'block';
      this.micIconOff.style.display = 'none';
    }
  }

  setMicDisabled(disabled) {
    this.micButton.disabled = disabled;
  }

  // ---- Camera Toggle ----

  setCameraActive(active) {
    if (active) {
      this.cameraToggle.classList.add('active');
      this.cameraToggle.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
          <circle cx="12" cy="13" r="4"/>
        </svg>
        Camera On`;
      this.cameraPlaceholder.classList.add('hidden');
    } else {
      this.cameraToggle.classList.remove('active');
      this.cameraToggle.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
          <circle cx="12" cy="13" r="4"/>
        </svg>
        Camera`;
      this.cameraPlaceholder.classList.remove('hidden');
    }
  }

  // ---- Session Timer ----

  startTimer() {
    this._sessionStart = Date.now();
    this._timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - this._sessionStart) / 1000);
      const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const secs = String(elapsed % 60).padStart(2, '0');
      this.timerEl.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  stopTimer() {
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }
    this.timerEl.textContent = '00:00';
  }

  // ---- Conversation Bubbles ----

  addTranscription(role, text) {
    if (this._conversationEmpty) {
      this._conversationEmpty.classList.add('hidden');
    }

    if (role === 'user') {
      if (!this._currentUserBubble) {
        this._currentUserBubble = this._createBubble('user');
      }
      this._currentUserBubble.querySelector('.bubble-text').textContent = text;
    } else {
      // Finalize previous user bubble
      this._currentUserBubble = null;

      if (!this._currentTutorBubble) {
        this._currentTutorBubble = this._createBubble('tutor');
      }
      this._currentTutorBubble.querySelector('.bubble-text').textContent = text;
    }

    this._scrollToBottom();
  }

  finalizeTurn() {
    this._currentUserBubble = null;
    this._currentTutorBubble = null;
  }

  _createBubble(role) {
    const wrapper = document.createElement('div');
    wrapper.className = `bubble bubble-${role}`;

    const label = document.createElement('div');
    label.className = 'bubble-label';
    label.textContent = role === 'user' ? 'You' : 'Luna';

    const text = document.createElement('div');
    text.className = 'bubble-text';

    wrapper.appendChild(label);
    wrapper.appendChild(text);
    this.conversationEl.appendChild(wrapper);
    return wrapper;
  }

  // ---- Feedback Cards ----

  addFeedbackCard(feedback) {
    if (this._feedbackEmpty) {
      this._feedbackEmpty.classList.add('hidden');
    }

    // If correct, trigger happy reaction
    if (feedback.is_correct) {
      this.triggerHappyReaction();
    }

    const card = document.createElement('div');
    card.className = `feedback-card ${feedback.is_correct ? 'correct' : 'has-errors'}`;

    // Header
    const header = document.createElement('div');
    header.className = 'feedback-card-header';

    const difficulty = document.createElement('span');
    difficulty.className = 'feedback-difficulty';
    difficulty.textContent = feedback.difficulty;

    const status = document.createElement('span');
    status.className = `feedback-status ${feedback.is_correct ? 'correct' : 'incorrect'}`;
    status.textContent = feedback.is_correct ? 'Correct!' : `${feedback.errors.length} error(s)`;

    header.appendChild(difficulty);
    header.appendChild(status);
    card.appendChild(header);

    // Corrected sentence
    if (!feedback.is_correct) {
      const corrected = document.createElement('div');
      corrected.className = 'corrected-sentence';
      corrected.textContent = feedback.corrected_sentence;
      card.appendChild(corrected);
    }

    // Error items
    for (const err of (feedback.errors || [])) {
      const item = document.createElement('div');
      item.className = 'error-item';

      const correction = document.createElement('div');
      correction.className = 'error-correction';
      correction.innerHTML = `
        <span class="error-original">${this._escapeHtml(err.original)}</span>
        <span class="error-arrow">&rarr;</span>
        <span class="error-fix">${this._escapeHtml(err.correction)}</span>
        <span class="error-type-badge error-type-${err.error_type}">${err.error_type.replace('_', ' ')}</span>
      `;

      const explanation = document.createElement('div');
      explanation.className = 'error-explanation';
      explanation.textContent = err.explanation;

      item.appendChild(correction);
      item.appendChild(explanation);
      card.appendChild(item);
    }

    this.feedbackCardsEl.prepend(card);
  }

  clearConversation() {
    this.conversationEl.innerHTML = '';
    this._conversationEmpty = null;
    this._currentUserBubble = null;
    this._currentTutorBubble = null;
  }

  _scrollToBottom() {
    this.conversationEl.scrollTop = this.conversationEl.scrollHeight;
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
