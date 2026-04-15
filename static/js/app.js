/**
 * Main application controller for the Pangea Voice Tutor.
 * Orchestrates WebSocket, audio capture/playback, video, waveform,
 * UI, and Luna avatar animations.
 */
(function () {
  'use strict';

  // ---- Module instances ----
  const wsClient = new WebSocketClient();
  const audioPlayback = new AudioPlayback();
  const waveformViz = new WaveformViz(document.getElementById('waveform-canvas'));
  const ui = new UIController();

  let audioCapture = null;
  let videoCapture = null;
  let isSessionActive = false;
  let isCameraActive = false;
  let isTutorSpeaking = false;

  // ---- DOM refs ----
  const micButton = document.getElementById('mic-button');
  const cameraToggle = document.getElementById('camera-toggle');
  const textInput = document.getElementById('text-input');
  const textSend = document.getElementById('text-send');
  const videoEl = document.getElementById('camera-preview');
  const videoCanvas = document.getElementById('video-canvas');

  // ---- WebSocket URL ----
  function getWsUrl() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/ws/voice-tutor`;
  }

  // ---- WebSocket handlers ----
  wsClient.onStatusChange = (status) => {
    ui.setStatus(status);
    if (status === 'disconnected' && isSessionActive) {
      ui.setLunaState('idle');
    }
  };

  wsClient.onAudioData = (pcmBuffer) => {
    audioPlayback.enqueue(pcmBuffer);
    // Luna speaks when receiving audio
    if (!isTutorSpeaking) {
      isTutorSpeaking = true;
      ui.setLunaState('speaking');
    }
  };

  wsClient.onMessage = (msg) => {
    switch (msg.type) {
      case 'session_ready':
        ui.setStatus('connected');
        ui.startTimer();
        ui.setLunaState('idle');
        break;

      case 'transcription':
        if (msg.transcription) {
          ui.addTranscription(msg.transcription.role, msg.transcription.text);
          if (msg.transcription.role === 'user') {
            ui.setLunaState('listening');
          }
        }
        break;

      case 'feedback':
        if (msg.feedback) {
          ui.addFeedbackCard(msg.feedback);
          // Happy reaction triggered inside addFeedbackCard for correct answers
        }
        break;

      case 'turn_start':
        isTutorSpeaking = true;
        ui.setLunaState('speaking');
        break;

      case 'turn_end':
        isTutorSpeaking = false;
        ui.setLunaState('listening');
        ui.finalizeTurn();
        break;

      case 'interrupted':
        // Barge-in: clear audio and reset Luna
        audioPlayback.clearQueue();
        isTutorSpeaking = false;
        ui.setLunaState('listening');
        ui.finalizeTurn();
        break;

      case 'session_resuming':
        ui.setStatus('connecting');
        ui.setLunaState('thinking-state');
        break;

      case 'session_ended':
        stopSession();
        break;

      case 'error':
        console.error('Server error:', msg.error);
        ui.setStatus('error');
        ui.setLunaState('idle');
        break;

      case 'pong':
        break;
    }
  };

  // ---- Session lifecycle ----

  async function startSession() {
    if (isSessionActive) return;

    try {
      ui.setMicDisabled(true);
      ui.setStatus('connecting');
      ui.setLunaState('thinking-state');

      // Initialize audio playback
      await audioPlayback.init();

      // Start mic capture
      audioCapture = new AudioCapture((pcmBuffer) => {
        wsClient.sendAudio(pcmBuffer);
      });
      await audioCapture.start();

      // Connect WebSocket
      wsClient.connect(getWsUrl());

      // Wait for connection
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Connection timeout')), 10000);
        const origOnStatus = wsClient.onStatusChange;
        wsClient.onStatusChange = (status) => {
          origOnStatus?.(status);
          if (status === 'connected') {
            clearTimeout(timeout);
            wsClient.onStatusChange = origOnStatus;
            resolve();
          }
        };
      });

      // Send session config
      const config = {
        target_language: document.getElementById('target-lang').value,
        native_language: document.getElementById('native-lang').value,
        proficiency: document.getElementById('proficiency').value,
        voice: document.getElementById('voice-select').value,
        enable_camera: isCameraActive,
      };

      wsClient.sendMessage({ type: 'session_start', config });

      // Set up waveform visualization
      waveformViz.setInputAnalyser(audioCapture.getAnalyser());
      waveformViz.setOutputAnalyser(audioPlayback.getAnalyser());
      waveformViz.start();

      isSessionActive = true;
      ui.setMicActive(true);
      ui.setMicDisabled(false);
      ui.setLunaState('listening');

      // Disable config during session
      document.querySelectorAll('.config-group select').forEach(s => s.disabled = true);

    } catch (err) {
      console.error('Failed to start session:', err);
      ui.setStatus('error');
      ui.setMicDisabled(false);
      ui.setLunaState('idle');
      cleanup();
    }
  }

  function stopSession() {
    if (!isSessionActive) return;
    isSessionActive = false;
    isTutorSpeaking = false;

    wsClient.sendMessage({ type: 'session_end' });
    cleanup();
  }

  function cleanup() {
    waveformViz.stop();
    ui.setMicActive(false);
    ui.stopTimer();
    ui.setLunaState('idle');

    if (audioCapture) {
      audioCapture.stop();
      audioCapture = null;
    }

    audioPlayback.clearQueue();
    wsClient.disconnect();

    // Re-enable config
    document.querySelectorAll('.config-group select').forEach(s => s.disabled = false);
  }

  // ---- Camera toggle ----

  async function toggleCamera() {
    if (isCameraActive) {
      if (videoCapture) {
        videoCapture.stop();
        videoCapture = null;
      }
      isCameraActive = false;
      ui.setCameraActive(false);
    } else {
      try {
        videoCapture = new VideoCapture((base64) => {
          if (isSessionActive) {
            wsClient.sendMessage({ type: 'video_frame', data: base64 });
          }
        });
        await videoCapture.start(videoEl, videoCanvas);
        isCameraActive = true;
        ui.setCameraActive(true);
      } catch (err) {
        console.error('Camera access denied:', err);
      }
    }
  }

  // ---- Text input fallback ----

  function sendTextMessage() {
    const text = textInput.value.trim();
    if (!text || !isSessionActive) return;
    wsClient.sendMessage({ type: 'text_input', data: text });
    ui.addTranscription('user', text);
    ui.finalizeTurn();
    ui.setLunaState('thinking-state');
    textInput.value = '';
  }

  // ---- Event listeners ----

  micButton.addEventListener('click', () => {
    if (isSessionActive) {
      stopSession();
    } else {
      startSession();
    }
  });

  cameraToggle.addEventListener('click', toggleCamera);
  textSend.addEventListener('click', sendTextMessage);
  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendTextMessage();
  });

  // Keep-alive ping
  setInterval(() => {
    if (isSessionActive && wsClient.isOpen) {
      wsClient.sendMessage({ type: 'ping' });
    }
  }, 30000);

  // Initialize Luna to idle state
  ui.setLunaState('idle');

})();
