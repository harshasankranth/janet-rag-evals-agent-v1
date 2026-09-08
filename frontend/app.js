const stateLabel = document.getElementById("state-label");
const subtitleLine = document.getElementById("subtitle-line");
const talkButton = document.getElementById("talk-button");
const waveCanvas = document.getElementById("wave-canvas");
const waveCtx = waveCanvas.getContext("2d");

const AMBER = "255, 182, 39";

let state = "idle";
let liveAmplitude = 0; // driven by "amplitude" events while listening
let demoMode = false; // real WS state/emotion/speech events are ignored while true

window.setDemoMode = (value) => {
  demoMode = value;
};

let envelope = null;
let envelopeStartMs = 0;
let envelopeDurationMs = 0;

let pendingSubtitle = ""; // full text of a janet reply, revealed over envelopeDurationMs
let revealedChars = 0;

const waveHistory = new Array(48).fill(0);

let socket = null;

function setState(newState) {
  state = newState;
  stateLabel.textContent = newState.toUpperCase();
  if (newState === "speaking") {
    talkButton.textContent = "INTERRUPT";
    talkButton.classList.add("speaking");
  } else {
    talkButton.textContent = "PRESS TO TALK";
    talkButton.classList.remove("speaking");
  }
  window.JanetAvatar.setState(newState);
}
window.setUIState = setState;
window.setUISubtitle = (text) => {
  pendingSubtitle = "";
  revealedChars = 0;
  subtitleLine.textContent = text || " ";
};

function sendTalk() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "talk" }));
  }
}

talkButton.addEventListener("click", sendTalk);
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat && document.activeElement !== talkButton) {
    e.preventDefault();
    sendTalk();
  }
});

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  socket = ws;
  ws.onopen = () => setState(state === "idle" ? "idle" : state);
  ws.onclose = () => setTimeout(connect, 1000);
  ws.onerror = () => ws.close();
  ws.onmessage = (msg) => {
    if (demoMode) return;
    const event = JSON.parse(msg.data);
    switch (event.type) {
      case "state":
        setState(event.value);
        if (event.value === "listening") {
          liveAmplitude = 0;
        }
        break;
      case "emotion":
        window.JanetAvatar.setEmotion(event.value);
        break;
      case "subtitle": // user's transcribed text — shown instantly
        pendingSubtitle = "";
        revealedChars = 0;
        subtitleLine.textContent = event.text || " ";
        break;
      case "amplitude":
        liveAmplitude = event.level;
        window.JanetAvatar.setAmplitude(event.level);
        break;
      case "speech": // janet's reply text + its waveform envelope, arrive together atomically
        pendingSubtitle = event.text;
        revealedChars = 0;
        envelope = event.envelope;
        envelopeDurationMs = event.duration * 1000;
        envelopeStartMs = performance.now();
        window.JanetAvatar.playSpeechEnvelope(event.duration, event.envelope);
        break;
    }
  };
}
connect();

function currentAmplitude(nowMs) {
  if (state === "listening") {
    return Math.min(liveAmplitude, 1.0);
  }
  if (state === "speaking" && envelope && envelope.length) {
    const elapsed = nowMs - envelopeStartMs;
    if (elapsed < 0) return 0;
    const idx = Math.floor((elapsed / envelopeDurationMs) * envelope.length);
    if (idx >= envelope.length) return 0;
    return envelope[idx];
  }
  if (state === "thinking") {
    return 0.25 + Math.sin(nowMs / 260) * 0.15;
  }
  return 0.12 + Math.sin(nowMs / 1600) * 0.1;
}

function drawWave(amp) {
  waveHistory.push(amp);
  waveHistory.shift();

  const w = waveCanvas.width;
  const h = waveCanvas.height;
  waveCtx.clearRect(0, 0, w, h);

  const barW = w / waveHistory.length;
  waveCtx.fillStyle = `rgba(${AMBER}, 0.7)`;
  waveHistory.forEach((v, i) => {
    const barH = Math.max(2, v * h);
    waveCtx.fillRect(i * barW, (h - barH) / 2, barW * 0.6, barH);
  });
}

function updateSubtitle(nowMs) {
  if (!pendingSubtitle) return;
  if (state !== "speaking" || !envelopeDurationMs) {
    subtitleLine.textContent = pendingSubtitle;
    return;
  }
  const elapsed = nowMs - envelopeStartMs;
  const progress = Math.max(0, Math.min(1, elapsed / envelopeDurationMs));
  const chars = Math.floor(progress * pendingSubtitle.length);
  if (chars !== revealedChars) {
    revealedChars = chars;
    subtitleLine.textContent = pendingSubtitle.slice(0, chars) || " ";
  }
}

function frame(nowMs) {
  const amp = currentAmplitude(nowMs);
  drawWave(amp);
  updateSubtitle(nowMs);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
