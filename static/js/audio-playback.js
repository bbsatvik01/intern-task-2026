/**
 * Audio playback engine for Gemini's PCM output.
 * Uses AudioWorklet for glitch-free playback at 24kHz.
 * Supports queue clearing for barge-in handling.
 */
class AudioPlayback {
  constructor() {
    this.playbackContext = null;
    this.workletNode = null;
    this.analyser = null;
    this._initialized = false;
  }

  async init() {
    // Create playback context at 24kHz (Gemini's output rate)
    this.playbackContext = new AudioContext({ sampleRate: 24000 });

    await this.playbackContext.audioWorklet.addModule('/static/js/worklets/playback-processor.js');

    this.workletNode = new AudioWorkletNode(this.playbackContext, 'playback-processor');

    // Analyser for output waveform visualization
    this.analyser = this.playbackContext.createAnalyser();
    this.analyser.fftSize = 2048;

    this.workletNode.connect(this.analyser);
    this.analyser.connect(this.playbackContext.destination);

    this._initialized = true;
  }

  /**
   * Enqueue raw Int16 PCM audio from Gemini for playback.
   * @param {ArrayBuffer} int16PcmBuffer
   */
  enqueue(int16PcmBuffer) {
    if (!this._initialized || !this.workletNode) return;

    // Resume context if suspended (browser autoplay policy)
    if (this.playbackContext.state === 'suspended') {
      this.playbackContext.resume();
    }

    // Convert Int16 -> Float32 for the worklet
    const int16 = new Int16Array(int16PcmBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    this.workletNode.port.postMessage({ type: 'audio', samples: float32 });
  }

  /**
   * Clear the playback queue immediately (barge-in).
   */
  clearQueue() {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'clear' });
    }
  }

  getAnalyser() {
    return this.analyser;
  }

  async destroy() {
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.analyser) {
      this.analyser.disconnect();
      this.analyser = null;
    }
    if (this.playbackContext) {
      await this.playbackContext.close().catch(() => {});
      this.playbackContext = null;
    }
    this._initialized = false;
  }
}
