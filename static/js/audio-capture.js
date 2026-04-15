/**
 * Microphone capture using AudioWorklet.
 * Outputs raw PCM Int16 chunks at 16kHz via the onChunk callback.
 */
class AudioCapture {
  constructor(onChunk) {
    this.onChunk = onChunk;  // (ArrayBuffer) => void
    this.stream = null;
    this.audioContext = null;
    this.workletNode = null;
    this.sourceNode = null;
    this.analyser = null;
    this._running = false;
  }

  async start() {
    // Request microphone with echo cancellation
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // Create AudioContext at 16kHz (Gemini's expected input rate)
    this.audioContext = new AudioContext({ sampleRate: 16000 });

    // Load the capture worklet
    await this.audioContext.audioWorklet.addModule('/static/js/worklets/capture-processor.js');

    this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);

    // Analyser for waveform visualization
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 2048;
    this.sourceNode.connect(this.analyser);

    // Worklet node for PCM extraction
    this.workletNode = new AudioWorkletNode(this.audioContext, 'capture-processor');
    this.workletNode.port.onmessage = (e) => {
      if (this._running) {
        this.onChunk(e.data);  // ArrayBuffer of Int16 PCM
      }
    };

    this.analyser.connect(this.workletNode);
    // Do NOT connect workletNode to destination (no local playback of mic)

    this._running = true;
  }

  stop() {
    this._running = false;
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.analyser) {
      this.analyser.disconnect();
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    this.analyser = null;
  }

  getAnalyser() {
    return this.analyser;
  }
}
