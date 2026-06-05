/**
 * AudioWorklet processor for PCM audio playback.
 * Runs on the audio rendering thread for glitch-free output.
 *
 * Receives Float32 audio chunks from the main thread and plays them
 * sequentially. Supports queue clearing for barge-in handling.
 */
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];       // Array of Float32Array chunks
    this.currentChunk = null;
    this.currentOffset = 0;

    this.port.onmessage = (e) => {
      if (e.data.type === 'audio') {
        this.queue.push(e.data.samples);
      } else if (e.data.type === 'clear') {
        // Barge-in: drop all buffered audio immediately
        this.queue = [];
        this.currentChunk = null;
        this.currentOffset = 0;
      }
    };
  }

  process(inputs, outputs) {
    const output = outputs[0]?.[0];
    if (!output) return true;

    let written = 0;

    while (written < output.length) {
      // Get next chunk if needed
      if (!this.currentChunk || this.currentOffset >= this.currentChunk.length) {
        if (this.queue.length === 0) {
          // Fill remaining with silence
          output.fill(0, written);
          return true;
        }
        this.currentChunk = this.queue.shift();
        this.currentOffset = 0;
      }

      const remaining = output.length - written;
      const available = this.currentChunk.length - this.currentOffset;
      const toCopy = Math.min(remaining, available);

      output.set(
        this.currentChunk.subarray(this.currentOffset, this.currentOffset + toCopy),
        written
      );

      written += toCopy;
      this.currentOffset += toCopy;
    }

    return true;
  }
}

registerProcessor('playback-processor', PlaybackProcessor);
