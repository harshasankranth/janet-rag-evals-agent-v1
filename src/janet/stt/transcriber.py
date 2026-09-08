"""Local speech-to-text via faster-whisper."""

import numpy as np
from faster_whisper import WhisperModel

from janet import config


class Transcriber:
    def __init__(self, model_size: str = config.WHISPER_MODEL_SIZE) -> None:
        self._model = WhisperModel(
            model_size,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        """Returns (text, detected_language) — language is an ISO 639-1 code
        (e.g. "en", "hi", "te") auto-detected per utterance, or None if the
        audio was empty."""
        if audio.size == 0:
            return "", None
        segments, info = self._model.transcribe(audio)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info.language
