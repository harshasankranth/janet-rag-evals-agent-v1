/* JanetAvatar — renders and animates the SVG character in index.html.
   Public API: setState, setEmotion, setAmplitude, playSpeechEnvelope,
   applyVisemeTimeline, stopSpeaking. Exposed as window.JanetAvatar. */

(function () {
  const EYE = {
    neutral: `<ellipse cx="0" cy="0" rx="15" ry="19" fill="var(--amber)"/><ellipse cx="6" cy="-3" rx="11" ry="15" fill="var(--face-dark)"/>`,
    happy: `<path d="M-15,3 Q0,-13 15,3" stroke="var(--amber)" stroke-width="5.5" fill="none" stroke-linecap="round"/>`,
    excited: `<path d="M0,-14 L4,-4 L14,0 L4,4 L0,14 L-4,4 L-14,0 L-4,-4 Z" fill="var(--amber)"/>`,
    curiousGlance: `<ellipse cx="0" cy="0" rx="15" ry="19" fill="var(--amber)"/><ellipse cx="-9" cy="-2" rx="10" ry="14" fill="var(--face-dark)"/>`,
    surprised: `<ellipse cx="0" cy="0" rx="17" ry="18" fill="var(--amber)"/><ellipse cx="3" cy="4" rx="5" ry="5" fill="var(--face-dark)"/>`,
    squint: `<rect x="-14" y="-3" width="28" height="6" rx="3" fill="var(--amber)"/>`,
    sleepy: `<path d="M-14,-2 Q0,4 14,-2" stroke="var(--amber)" stroke-width="4.5" fill="none" stroke-linecap="round"/>`,
    thinkingGaze: `<ellipse cx="0" cy="0" rx="15" ry="19" fill="var(--amber)"/><ellipse cx="7" cy="7" rx="10" ry="13" fill="var(--face-dark)"/>`,
    blink: `<rect x="-14" y="-2" width="28" height="4" rx="2" fill="var(--amber)"/>`,
  };

  const MOUTH = {
    neutral: `<rect x="-9" y="-2" width="18" height="4" rx="2" fill="var(--amber)"/>`,
    happy: `<path d="M-11,-3 Q0,9 11,-3" stroke="var(--amber)" stroke-width="4.5" fill="none" stroke-linecap="round"/>`,
    excited: `<path d="M-13,-3 Q0,12 13,-3 Q0,3 -13,-3 Z" fill="var(--amber)"/>`,
    curious: `<ellipse cx="0" cy="0" rx="4" ry="5" fill="var(--amber)"/>`,
    surprised: `<ellipse cx="0" cy="2" rx="8" ry="10" fill="var(--amber)"/>`,
    confused: `<path d="M-11,0 Q-5.5,4 0,0 Q5.5,-4 11,0" stroke="var(--amber)" stroke-width="4" fill="none" stroke-linecap="round"/>`,
    sleepy: `<ellipse cx="0" cy="2" rx="3.5" ry="2.5" fill="var(--amber)"/>`,
    thinking: `<line x1="-7" y1="0" x2="7" y2="1" stroke="var(--amber)" stroke-width="4" stroke-linecap="round"/>`,
  };

  const ACCESSORY = {
    question: `<text x="0" y="0" font-size="26" fill="var(--amber)" text-anchor="middle" font-family="ui-monospace,monospace">?</text>`,
    exclaim: `<text x="0" y="0" font-size="26" fill="var(--amber)" text-anchor="middle" font-family="ui-monospace,monospace">!</text>`,
    zzz: `<text x="0" y="0" font-size="20" fill="var(--amber)" text-anchor="middle" font-family="ui-monospace,monospace">z z z</text>`,
    dots: `<text x="0" y="0" font-size="24" fill="var(--amber)" text-anchor="middle" font-family="ui-monospace,monospace">...</text>`,
  };

  const EMOTIONS = {
    neutral: { left: EYE.neutral, right: EYE.neutral, mouth: MOUTH.neutral, accessory: null },
    happy: { left: EYE.happy, right: EYE.happy, mouth: MOUTH.happy, accessory: null },
    excited: { left: EYE.excited, right: EYE.excited, mouth: MOUTH.excited, accessory: null },
    curious: { left: EYE.neutral, right: EYE.curiousGlance, mouth: MOUTH.curious, accessory: "question" },
    surprised: { left: EYE.surprised, right: EYE.surprised, mouth: MOUTH.surprised, accessory: "exclaim" },
    confused: { left: EYE.neutral, right: EYE.squint, mouth: MOUTH.confused, accessory: null },
    sleepy: { left: EYE.sleepy, right: EYE.sleepy, mouth: MOUTH.sleepy, accessory: "zzz" },
    thinking: { left: EYE.thinkingGaze, right: EYE.neutral, mouth: MOUTH.thinking, accessory: "dots" },
  };

  // Discrete mouth shapes for viseme-driven lip-sync (used if a TTS provider
  // ever supplies phoneme/viseme timing; falls back to amplitude otherwise).
  const VISEME_MOUTHS = {
    closed: `<rect x="-7" y="-1" width="14" height="3" rx="1.5" fill="var(--amber)"/>`,
    mid: `<ellipse cx="0" cy="1" rx="7" ry="5" fill="var(--amber)"/>`,
    open: `<ellipse cx="0" cy="2" rx="9" ry="10" fill="var(--amber)"/>`,
    wide: `<ellipse cx="0" cy="1" rx="12" ry="4" fill="var(--amber)"/>`,
  };

  function el(id) {
    return document.getElementById(id);
  }

  const nodes = {};
  let ready = false;

  function ensureNodes() {
    if (ready) return;
    nodes.head = el("head");
    nodes.body = el("body");
    nodes.halo = el("halo");
    nodes.network = el("network");
    nodes.eyeLeft = el("eye-left");
    nodes.eyeRight = el("eye-right");
    nodes.mouth = el("mouth");
    nodes.accessory = el("accessory");
    ready = true;
  }

  let currentState = "idle";
  let currentEmotion = "neutral";
  let listeningAmplitude = 0;
  let blinking = false;
  let nextBlinkAt = 0;

  let envelope = null;
  let envelopeStartMs = 0;
  let envelopeDurationMs = 0;
  let visemeTimeline = null;

  function randomBlinkDelay() {
    return 3000 + Math.random() * 3000;
  }

  function applyEmotionVisuals() {
    ensureNodes();
    const preset = EMOTIONS[currentEmotion] || EMOTIONS.neutral;
    if (!blinking) {
      nodes.eyeLeft.innerHTML = preset.left;
      nodes.eyeRight.innerHTML = preset.right;
    }
    if (currentState !== "speaking") {
      nodes.mouth.innerHTML = preset.mouth;
    }
    if (preset.accessory) {
      nodes.accessory.innerHTML = ACCESSORY[preset.accessory];
      nodes.accessory.style.opacity = "0.85";
    } else {
      nodes.accessory.style.opacity = "0";
    }
  }

  function updateBlink(nowMs) {
    if (currentState === "speaking") return; // keep eyes on the listener while talking
    if (!blinking && nowMs >= nextBlinkAt) {
      blinking = true;
      nodes.eyeLeft.innerHTML = EYE.blink;
      nodes.eyeRight.innerHTML = EYE.blink;
      setTimeout(() => {
        blinking = false;
        applyEmotionVisuals();
        nextBlinkAt = performance.now() + randomBlinkDelay();
      }, 130);
    }
  }

  const DEFAULT_EMOTION_FOR_STATE = {
    idle: "neutral",
    listening: "curious",
    thinking: "thinking",
    speaking: "happy",
  };

  function setState(state) {
    ensureNodes();
    currentState = state;
    nodes.network.classList.toggle("spin-fast", state === "thinking" || state === "speaking");
    nodes.network.classList.toggle("spin-slow", state === "idle" || state === "listening");
    if (state !== "speaking") {
      envelope = null;
      visemeTimeline = null;
    }
    setEmotion(DEFAULT_EMOTION_FOR_STATE[state] || "neutral");
  }

  function setEmotion(emotion) {
    if (!EMOTIONS[emotion]) return;
    currentEmotion = emotion;
    applyEmotionVisuals();
  }

  function setAmplitude(level) {
    listeningAmplitude = Math.min(Math.max(level, 0), 1);
  }

  function playSpeechEnvelope(durationSeconds, envelopeArray) {
    envelope = envelopeArray;
    envelopeDurationMs = durationSeconds * 1000;
    envelopeStartMs = performance.now();
    visemeTimeline = null;
  }

  function applyVisemeTimeline(timeline) {
    // timeline: [{offsetMs, viseme}], viseme in closed|mid|open|wide
    visemeTimeline = timeline && timeline.length ? timeline : null;
  }

  function stopSpeaking() {
    envelope = null;
    visemeTimeline = null;
  }

  function speakingAmplitude(nowMs) {
    if (!envelope || !envelope.length) return 0;
    const elapsed = nowMs - envelopeStartMs;
    if (elapsed < 0) return 0;
    const idx = Math.floor((elapsed / envelopeDurationMs) * envelope.length);
    if (idx >= envelope.length) return 0;
    return envelope[idx];
  }

  function updateMouthForSpeech(nowMs, amp) {
    if (visemeTimeline) {
      const elapsed = nowMs - envelopeStartMs;
      let current = visemeTimeline[0];
      for (const entry of visemeTimeline) {
        if (entry.offsetMs <= elapsed) current = entry;
        else break;
      }
      nodes.mouth.innerHTML = VISEME_MOUTHS[current.viseme] || VISEME_MOUTHS.mid;
      return;
    }
    const openAmount = amp;
    nodes.mouth.innerHTML =
      `<ellipse cx="0" cy="${2 + openAmount * 4}" rx="${6 + openAmount * 4}" ry="${2 + openAmount * 12}" fill="var(--amber)"/>`;
  }

  function frame(nowMs) {
    ensureNodes();
    updateBlink(nowMs);

    let headTransform = "";
    let bodyTransform = "";
    let haloTransform = "";
    let networkOpacity = 0.5;

    if (currentState === "idle") {
      const floatY = Math.sin(nowMs / 1400) * 6;
      const breathe = 1 + Math.sin(nowMs / 1800) * 0.015;
      headTransform = `translateY(${floatY}px)`;
      bodyTransform = `translateY(${floatY * 0.6}px) scale(${breathe})`;
      haloTransform = `translateY(${floatY}px)`;
      networkOpacity = 0.35;
    } else if (currentState === "listening") {
      const floatY = Math.sin(nowMs / 1400) * 4;
      const nod = (listeningAmplitude - 0.2) * 6;
      headTransform = `translateY(${floatY}px) rotate(${nod}deg)`;
      bodyTransform = `translateY(${floatY * 0.5}px)`;
      haloTransform = `translateY(${floatY}px)`;
      networkOpacity = 0.45 + listeningAmplitude * 0.3;
    } else if (currentState === "thinking") {
      const tilt = 9 + Math.sin(nowMs / 900) * 3;
      const floatY = Math.sin(nowMs / 1600) * 4;
      headTransform = `translateY(${floatY}px) rotate(${tilt}deg)`;
      bodyTransform = `translateY(${floatY * 0.5}px)`;
      haloTransform = `translateY(${floatY}px) rotate(${tilt * 0.5}deg)`;
      networkOpacity = 0.7;
    } else if (currentState === "speaking") {
      const amp = speakingAmplitude(nowMs);
      const bob = Math.sin(nowMs / 140) * amp * 3;
      headTransform = `translateY(${-amp * 3 + bob}px)`;
      bodyTransform = `translateY(${-amp * 5}px)`;
      haloTransform = `translateY(${-amp * 3}px)`;
      networkOpacity = 0.5 + amp * 0.5;
      updateMouthForSpeech(nowMs, amp);
    }

    nodes.head.style.transform = headTransform;
    nodes.body.style.transform = bodyTransform;
    nodes.halo.style.transform = haloTransform;
    nodes.network.style.opacity = String(networkOpacity);

    requestAnimationFrame(frame);
  }

  function init() {
    ensureNodes();
    nextBlinkAt = performance.now() + randomBlinkDelay();
    setState("idle");
    requestAnimationFrame(frame);
  }

  window.JanetAvatar = {
    init,
    setState,
    setEmotion,
    setAmplitude,
    playSpeechEnvelope,
    applyVisemeTimeline,
    stopSpeaking,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
