"""Short synthetic ping tones used as audio cues (no external sound files needed)."""

import time

import numpy as np
import sounddevice as sd

_SAMPLE_RATE = 22_050
_FADE_S = 0.01


def _tone(freq: float, duration: float) -> np.ndarray:
    t = np.linspace(0, duration, int(_SAMPLE_RATE * duration), endpoint=False)
    wave = 0.25 * np.sin(2 * np.pi * freq * t).astype(np.float32)

    fade_len = int(_FADE_S * _SAMPLE_RATE)
    envelope = np.ones_like(wave)
    envelope[:fade_len] = np.linspace(0, 1, fade_len, dtype=np.float32)
    envelope[-fade_len:] = np.linspace(1, 0, fade_len, dtype=np.float32)
    return wave * envelope


def play_wake_detected() -> None:
    """Cue that the wake word was heard and Janet is now recording the command."""
    sd.play(np.concatenate([_tone(784, 0.08), _tone(1046, 0.1)]), samplerate=_SAMPLE_RATE)
    sd.wait()


def play_listening_done() -> None:
    """Cue that the utterance was captured and Janet is now thinking."""
    sd.play(_tone(880, 0.12), samplerate=_SAMPLE_RATE)
    sd.wait()


def play_answer_ready() -> None:
    """Cue that Janet is about to speak its reply."""
    sd.play(np.concatenate([_tone(660, 0.09), _tone(990, 0.09)]), samplerate=_SAMPLE_RATE)
    sd.wait()


def play_listening_started() -> None:
    """Cue that Janet has finished speaking and is back to waiting for the wake word.

    Called immediately after Piper playback ends, so a brief settle delay is
    needed first — opening a new output stream right away can otherwise clip
    or silently drop the tone on Windows.
    """
    time.sleep(0.2)
    sd.play(np.tile(_tone(523, 0.18), 2), samplerate=_SAMPLE_RATE)
    sd.wait()
