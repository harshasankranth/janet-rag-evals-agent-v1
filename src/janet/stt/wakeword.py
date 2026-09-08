"""Wake-word detection via openWakeWord — blocks until "Hey Janet" is heard."""

import threading
from pathlib import Path

import openwakeword
import sounddevice as sd
from openwakeword.model import Model

from janet import config

_SAMPLE_RATE = 16_000
_CHUNK_SIZE = 1280  # 80ms at 16kHz, openWakeWord's recommended frame size
_THRESHOLD = 0.5


class WakeWordDetector:
    def __init__(self, model_path: str | None = None) -> None:
        model_path = model_path or config.WAKE_WORD_MODEL
        if not model_path:
            raise RuntimeError(
                "WAKE_WORD_MODEL is not set. Train a \"Hey Janet\" model (see .env.example) "
                "and point WAKE_WORD_MODEL at the resulting .onnx file."
            )
        if not Path(model_path).exists():
            raise RuntimeError(f"WAKE_WORD_MODEL points to a missing file: {model_path}")

        openwakeword.utils.download_models()  # shared feature-extraction models; no-op if already present
        self._model = Model(wakeword_models=[model_path], inference_framework="onnx")
        self._model_name = Path(model_path).stem

    def wait_for_wake_word(self) -> None:
        """Blocks until the wake word is detected."""
        with sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16", blocksize=_CHUNK_SIZE) as stream:
            while True:
                block, _overflowed = stream.read(_CHUNK_SIZE)
                scores = self._model.predict(block[:, 0])
                score = scores[self._model_name] if isinstance(scores, dict) else scores
                if score > _THRESHOLD:
                    return

    def close(self) -> None:
        pass


class PushToTalkDetector:
    """Fallback used when no wake-word model is configured: waits for Enter
    instead of listening for a spoken wake word. Same interface as
    WakeWordDetector so main.py doesn't need to branch on which is active."""

    def wait_for_wake_word(self) -> None:
        input("Press Enter to talk to Janet... ")

    def close(self) -> None:
        pass


class BrowserPushToTalkDetector:
    """Push-to-talk driven by the HUD's TALK button/keybind instead of the
    terminal — used when the browser HUD is enabled so the user never needs
    to alt-tab back to the CLI. Same interface as WakeWordDetector."""

    def __init__(self, talk_event: threading.Event) -> None:
        self._talk_event = talk_event

    def wait_for_wake_word(self) -> None:
        # Polling with a timeout (rather than a plain wait()) matters on
        # Windows: an unbounded threading.Event.wait() is a raw blocking
        # call that never hands control back to the interpreter, so
        # Ctrl+C/KeyboardInterrupt can't be delivered until it returns.
        while not self._talk_event.wait(timeout=0.2):
            pass
        self._talk_event.clear()

    def close(self) -> None:
        pass
