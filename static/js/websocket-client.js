/**
 * WebSocket client for the voice tutor.
 *
 * Protocol:
 *   Binary frames = raw PCM audio (no base64 overhead)
 *   Text frames   = JSON control messages
 */
class WebSocketClient {
  constructor() {
    this.ws = null;
    this.url = null;
    this.onAudioData = null;   // (ArrayBuffer) => void
    this.onMessage = null;     // (object) => void
    this.onStatusChange = null; // (string) => void
    this._reconnectTimer = null;
    this._reconnectDelay = 1000;
    this._maxReconnectDelay = 30000;
    this._shouldReconnect = false;
  }

  connect(url) {
    this.url = url;
    this._shouldReconnect = true;
    this._doConnect();
  }

  _doConnect() {
    if (this.ws) {
      try { this.ws.close(); } catch (_) {}
    }

    this.onStatusChange?.('connecting');
    this.ws = new WebSocket(this.url);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this._reconnectDelay = 1000;
      this.onStatusChange?.('connected');
    };

    this.ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        this.onAudioData?.(event.data);
      } else {
        try {
          const msg = JSON.parse(event.data);
          this.onMessage?.(msg);
        } catch (_) {}
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after this
    };

    this.ws.onclose = () => {
      this.onStatusChange?.('disconnected');
      if (this._shouldReconnect) {
        this._scheduleReconnect();
      }
    };
  }

  _scheduleReconnect() {
    if (this._reconnectTimer) return;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
      this._doConnect();
    }, this._reconnectDelay);
  }

  sendAudio(pcmArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(pcmArrayBuffer);
    }
  }

  sendMessage(obj) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  disconnect() {
    this._shouldReconnect = false;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.onStatusChange?.('disconnected');
  }

  get isOpen() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
