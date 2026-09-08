"""Selects a Synthesizer based on the TTS_PROVIDER env var."""

from janet import config
from janet.tts.synthesizers import (
    EdgeTTSSynthesizer,
    ElevenLabsSynthesizer,
    PiperSynthesizer,
    SarvamSynthesizer,
    Synthesizer,
)

_PROVIDERS: dict[str, type[Synthesizer]] = {
    "piper": PiperSynthesizer,
    "elevenlabs": ElevenLabsSynthesizer,
    "sarvam": SarvamSynthesizer,
    "edge_tts": EdgeTTSSynthesizer,
}


def get_synthesizer(name: str | None = None) -> Synthesizer:
    key = (name or config.TTS_PROVIDER).lower()
    if key not in _PROVIDERS:
        raise ValueError(f"Unknown TTS_PROVIDER {key!r}. Valid options: {', '.join(_PROVIDERS)}")
    return _PROVIDERS[key]()
