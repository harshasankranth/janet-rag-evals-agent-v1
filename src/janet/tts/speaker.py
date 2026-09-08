"""Text-to-speech playback: synthesizes via a pluggable backend (see
tts/synthesizers.py, selected by TTS_PROVIDER) then plays the result. The
interrupt hook and the HUD's waveform-envelope callback are provider-agnostic
playback concerns, handled once here regardless of which backend spoke.

If the primary provider fails (e.g. a cloud quota is exhausted), Speaker
falls back to TTS_FALLBACK_PROVIDER for the rest of the session rather than
going silent."""

import re
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from janet import config
from janet.tts.factory import get_synthesizer

_HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
_LIST_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_MARKDOWN_CHARS_RE = re.compile(r"[*_#`]+")

_ENVELOPE_WINDOW_S = 0.03  # matches recorder.py's block cadence


def _strip_markdown(text: str) -> str:
    """TTS engines read symbols literally ('#' -> "hash", '*' -> "asterisk"),
    so strip common markdown formatting before handing text off."""
    text = _HR_RE.sub(" ", text)
    text = _LIST_BULLET_RE.sub("", text)
    text = _MARKDOWN_CHARS_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _amplitude_envelope(audio: np.ndarray, sample_rate: int) -> list[float]:
    """RMS amplitude per ~30ms window, normalized to roughly [0, 1]."""
    window = max(1, int(sample_rate * _ENVELOPE_WINDOW_S))
    levels = [
        float(np.sqrt(np.mean(np.square(audio[i : i + window]))))
        for i in range(0, len(audio), window)
    ]
    peak = max(levels, default=0.0) or 1.0
    return [min(level / peak, 1.0) for level in levels]


class Speaker:
    def __init__(self) -> None:
        self._synth = get_synthesizer()
        self._fallback_synth = (
            get_synthesizer(config.TTS_FALLBACK_PROVIDER) if config.TTS_FALLBACK_PROVIDER else None
        )
        self._use_fallback = False

    def _synthesize(self, text: str, language: str | None) -> tuple[np.ndarray, int]:
        if not self._use_fallback:
            try:
                return self._synth.synthesize(text, language=language), self._synth.sample_rate
            except RuntimeError as exc:
                if self._fallback_synth is None:
                    raise
                print(
                    f"[warning] TTS provider {config.TTS_PROVIDER!r} failed ({exc}); "
                    f"falling back to {config.TTS_FALLBACK_PROVIDER!r} for the rest of this session."
                )
                self._use_fallback = True
        return (
            self._fallback_synth.synthesize(text, language=language),
            self._fallback_synth.sample_rate,
        )

    def speak(
        self,
        text: str,
        on_start: Callable[[float, list[float]], None] | None = None,
        interrupt: threading.Event | None = None,
        language: str | None = None,
    ) -> bool:
        """Speaks text aloud. Returns True if cut short via `interrupt`.
        `language` is an ISO 639-1 hint (e.g. "hi"/"te") for backends that
        support multiple languages per voice."""
        text = _strip_markdown(text)
        if not text:
            return False
        audio, sample_rate = self._synthesize(text, language)
        if audio.size == 0:
            return False
        if on_start:
            duration = len(audio) / sample_rate
            on_start(duration, _amplitude_envelope(audio, sample_rate))
        sd.play(audio, samplerate=sample_rate)

        if interrupt is None:
            sd.wait()
            return False

        while sd.get_stream().active:
            if interrupt.is_set():
                sd.stop()
                return True
            time.sleep(0.05)
        return False
