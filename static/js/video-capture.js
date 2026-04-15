/**
 * Camera capture for visual vocabulary teaching.
 * Captures JPEG frames at 1fps via canvas and sends as base64.
 */
class VideoCapture {
  constructor(onFrame) {
    this.onFrame = onFrame;   // (base64String) => void
    this.stream = null;
    this.videoEl = null;
    this.canvas = null;
    this.ctx = null;
    this._interval = null;
    this._active = false;
  }

  /**
   * Start camera capture.
   * @param {HTMLVideoElement} videoEl - Video element for preview
   * @param {HTMLCanvasElement} canvas - Canvas for frame extraction
   */
  async start(videoEl, canvas) {
    this.videoEl = videoEl;
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    this.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: 'user',
      },
    });

    this.videoEl.srcObject = this.stream;
    this.videoEl.classList.add('active');

    // Wait for video to be ready
    await new Promise((resolve) => {
      this.videoEl.onloadedmetadata = resolve;
    });

    // Set canvas size to match video
    this.canvas.width = 640;
    this.canvas.height = 480;

    this._active = true;

    // Capture frames at 1fps
    this._interval = setInterval(() => {
      if (!this._active) return;
      this.ctx.drawImage(this.videoEl, 0, 0, 640, 480);
      // JPEG at 70% quality
      const dataUrl = this.canvas.toDataURL('image/jpeg', 0.7);
      // Strip the data:image/jpeg;base64, prefix
      const base64 = dataUrl.split(',')[1];
      this.onFrame(base64);
    }, 1000);
  }

  stop() {
    this._active = false;
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
      this.videoEl.classList.remove('active');
    }
  }

  get isActive() {
    return this._active;
  }
}
