/**
 * Real-time waveform visualization using Canvas + AnalyserNode.
 * Draws input (mic) and output (tutor) waveforms with distinct colors.
 */
class WaveformViz {
  constructor(canvasEl) {
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext('2d');
    this.inputAnalyser = null;
    this.outputAnalyser = null;
    this._animFrame = null;
    this._running = false;

    // Colors (Pangea brand)
    this.inputColor = '#0ea5e9';   // primary blue
    this.outputColor = '#22c55e';  // green
    this.bgColor = '#f9fafb';      // gray-50

    this._resize();
    window.addEventListener('resize', () => this._resize());
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = rect.width * (window.devicePixelRatio || 1);
    this.canvas.height = rect.height * (window.devicePixelRatio || 1);
    this.ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
    this.width = rect.width;
    this.height = rect.height;
  }

  setInputAnalyser(analyser) {
    this.inputAnalyser = analyser;
  }

  setOutputAnalyser(analyser) {
    this.outputAnalyser = analyser;
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._draw();
  }

  stop() {
    this._running = false;
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
    this._clear();
  }

  _draw() {
    if (!this._running) return;

    this.ctx.fillStyle = this.bgColor;
    this.ctx.fillRect(0, 0, this.width, this.height);

    // Draw input waveform (top half)
    if (this.inputAnalyser) {
      this._drawWaveform(this.inputAnalyser, this.inputColor, 0, this.height / 2);
    }

    // Draw output waveform (bottom half)
    if (this.outputAnalyser) {
      this._drawWaveform(this.outputAnalyser, this.outputColor, this.height / 2, this.height / 2);
    }

    // Center divider line
    this.ctx.strokeStyle = '#e5e7eb';
    this.ctx.lineWidth = 0.5;
    this.ctx.beginPath();
    this.ctx.moveTo(0, this.height / 2);
    this.ctx.lineTo(this.width, this.height / 2);
    this.ctx.stroke();

    this._animFrame = requestAnimationFrame(() => this._draw());
  }

  _drawWaveform(analyser, color, yOffset, height) {
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    analyser.getByteTimeDomainData(dataArray);

    this.ctx.lineWidth = 1.5;
    this.ctx.strokeStyle = color;
    this.ctx.beginPath();

    const sliceWidth = this.width / bufferLength;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;  // Normalize to [0, 2]
      const y = yOffset + (v * height) / 2;

      if (i === 0) {
        this.ctx.moveTo(x, y);
      } else {
        this.ctx.lineTo(x, y);
      }
      x += sliceWidth;
    }

    this.ctx.stroke();
  }

  _clear() {
    this.ctx.fillStyle = this.bgColor;
    this.ctx.fillRect(0, 0, this.width, this.height);
  }
}
