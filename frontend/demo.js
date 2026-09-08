/* Demo/mock mode — exercises the full state machine and emotion set with no
   backend, no API keys. Toggled via the DEMO button in the topbar. */

(function () {
  const demoToggle = document.getElementById("demo-toggle");
  const emotionPanel = document.getElementById("emotion-panel");

  let active = false;
  let cancelled = false;
  let amplitudeTimer = null;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function fakeEnvelope(length) {
    const out = [];
    for (let i = 0; i < length; i++) {
      out.push(Math.min(1, Math.abs(Math.sin(i * 0.5)) * 0.6 + Math.random() * 0.35));
    }
    return out;
  }

  function fakeVisemeTimeline(durationMs) {
    const shapes = ["closed", "mid", "open", "wide", "mid", "open"];
    const timeline = [];
    let t = 0;
    let i = 0;
    while (t < durationMs) {
      timeline.push({ offsetMs: t, viseme: shapes[i % shapes.length] });
      t += 160 + Math.random() * 120;
      i++;
    }
    return timeline;
  }

  function startListeningWiggle() {
    stopListeningWiggle();
    amplitudeTimer = setInterval(() => {
      window.JanetAvatar.setAmplitude(0.2 + Math.random() * 0.6);
    }, 120);
  }

  function stopListeningWiggle() {
    if (amplitudeTimer) {
      clearInterval(amplitudeTimer);
      amplitudeTimer = null;
    }
  }

  async function runCycle() {
    while (!cancelled) {
      window.setUIState("idle");
      window.setUISubtitle("");
      await sleep(2200);
      if (cancelled) break;

      window.setUIState("listening");
      startListeningWiggle();
      await sleep(2200);
      stopListeningWiggle();
      if (cancelled) break;

      window.setUIState("thinking");
      await sleep(1800);
      if (cancelled) break;

      window.setUIState("speaking");
      const duration = 3.2;
      const envelope = fakeEnvelope(48);
      window.setUISubtitle("This is a demo of Janet speaking, with a simulated waveform and viseme timeline.");
      window.JanetAvatar.playSpeechEnvelope(duration, envelope);
      window.JanetAvatar.applyVisemeTimeline(fakeVisemeTimeline(duration * 1000));
      await sleep(duration * 1000 + 300);
      if (cancelled) break;
    }
  }

  function setActive(value) {
    active = value;
    window.setDemoMode(value);
    demoToggle.classList.toggle("active", value);
    emotionPanel.hidden = !value;

    if (value) {
      cancelled = false;
      runCycle();
    } else {
      cancelled = true;
      stopListeningWiggle();
      window.JanetAvatar.stopSpeaking();
      window.setUIState("idle");
      window.setUISubtitle("");
    }
  }

  demoToggle.addEventListener("click", () => setActive(!active));

  emotionPanel.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      window.JanetAvatar.setEmotion(chip.dataset.emotion);
    });
  });
})();
