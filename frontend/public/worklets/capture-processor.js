/**
 * AudioWorklet processor for microphone PCM capture.
 * Runs on the audio rendering thread for low-latency processing.
 *
 * Accumulates Float32 samples from the mic, converts to Int16 PCM,
 * and posts ~250ms chunks to the main thread via MessagePort.
 */
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(0);
    // ~250ms chunks at 16kHz = 4000 samples
    this.CHUNK_SIZE = 4000;
  }

  process(inputs) {
    const input = inputs[0]?.[0]; // Mono channel 0
    if (!input || input.length === 0) return true;

    // Accumulate incoming samples
    const newBuf = new Float32Array(this.buffer.length + input.length);
    newBuf.set(this.buffer);
    newBuf.set(input, this.buffer.length);
    this.buffer = newBuf;

    // Send complete chunks
    while (this.buffer.length >= this.CHUNK_SIZE) {
      const chunk = this.buffer.slice(0, this.CHUNK_SIZE);
      this.buffer = this.buffer.slice(this.CHUNK_SIZE);

      // Float32 [-1, 1] -> Int16 PCM [-32768, 32767]
      const pcm = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }

      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }

    return true;
  }
}

registerProcessor('capture-processor', CaptureProcessor);
