"""Pluggable TTS synthesis backends. Each turns text into raw float32 mono
PCM audio at its own sample rate; playback, interruption, and the HUD's
waveform envelope are provider-agnostic concerns handled once in speaker.py."""

import asyncio
import base64
import io
import wave
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from janet import config

_SARVAM_LANGUAGE_CODES = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}


class Synthesizer(ABC):
    sample_rate: int

    @abstractmethod
    def synthesize(self, text: str, language: str | None = None) -> np.ndarray:
        """language is an ISO 639-1 hint (e.g. "en"/"hi"/"te") from the
        detected input language; backends that don't need it ignore it."""
        ...


class PiperSynthesizer(Synthesizer):
    """Local, offline, fast — but noticeably synthetic prosody."""

    def __init__(self, model_path: str | None = None) -> None:
        from piper import PiperVoice

        model_path = model_path or config.PIPER_VOICE_MODEL
        if not model_path:
            raise RuntimeError(
                "PIPER_VOICE_MODEL is not set. Point it at a local Piper .onnx "
                "voice file — see .env.example."
            )
        path = Path(model_path)
        if not path.exists():
            raise RuntimeError(
                f"PIPER_VOICE_MODEL points to a missing file: {path}. Download a "
                "voice (.onnx + .onnx.json) from https://huggingface.co/rhasspy/piper-voices."
            )
        self._voice = PiperVoice.load(str(path))
        self.sample_rate = self._voice.config.sample_rate

    def synthesize(self, text: str, language: str | None = None) -> np.ndarray:
        chunks = [chunk.audio_float_array for chunk in self._voice.synthesize(text)]
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)


class ElevenLabsSynthesizer(Synthesizer):
    """Cloud, natural human-like prosody/pauses/accents. Needs an API key
    and a voice ID — see .env.example for where to find both."""

    _OUTPUT_FORMAT = "pcm_24000"  # raw headerless 16-bit PCM, no decoder needed

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        from elevenlabs import ElevenLabs

        api_key = api_key or config.ELEVENLABS_API_KEY
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set. Get a key from "
                "https://elevenlabs.io/app/settings/api-keys and set it in .env."
            )
        voice_id = voice_id or config.ELEVENLABS_VOICE_ID
        if not voice_id:
            raise RuntimeError(
                "ELEVENLABS_VOICE_ID is not set. Pick a voice from "
                "https://elevenlabs.io/app/voice-library, copy its Voice ID, and "
                "set ELEVENLABS_VOICE_ID in .env."
            )
        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model_id = model_id or config.ELEVENLABS_MODEL
        self.sample_rate = 24_000  # matches _OUTPUT_FORMAT above

    def synthesize(self, text: str, language: str | None = None) -> np.ndarray:
        language_kwargs = {"language_code": language} if language else {}
        try:
            chunks = list(
                self._client.text_to_speech.convert(
                    self._voice_id,
                    text=text,
                    model_id=self._model_id,
                    output_format=self._OUTPUT_FORMAT,
                    **language_kwargs,
                )
            )
        except Exception as exc:
            raise RuntimeError(f"Could not reach ElevenLabs: {exc}") from exc
        raw = b"".join(chunks)
        if not raw:
            return np.zeros(0, dtype=np.float32)
        audio_int16 = np.frombuffer(raw, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0


class SarvamSynthesizer(Synthesizer):
    """Cloud, purpose-built for Indian languages — natural Hindi/Telugu (and
    English) speech. Needs an API key — see .env.example."""

    def __init__(
        self,
        api_key: str | None = None,
        speaker: str | None = None,
        model: str | None = None,
    ) -> None:
        from sarvamai import SarvamAI

        api_key = api_key or config.SARVAM_API_KEY
        if not api_key:
            raise RuntimeError(
                "SARVAM_API_KEY is not set. Get a key from "
                "https://dashboard.sarvam.ai and set it in .env."
            )
        self._client = SarvamAI(api_subscription_key=api_key)
        self._speaker = speaker or config.SARVAM_SPEAKER
        self._model = model or config.SARVAM_MODEL
        self.sample_rate = 22_050  # updated from the actual WAV header per call

    def synthesize(self, text: str, language: str | None = None) -> np.ndarray:
        language_code = _SARVAM_LANGUAGE_CODES.get(language or "en", "en-IN")
        try:
            response = self._client.text_to_speech.convert(
                text=text,
                language_code=language_code,
                speaker=self._speaker,
                model=self._model,
                output_audio_codec="wav",
            )
        except Exception as exc:
            raise RuntimeError(f"Could not reach Sarvam AI: {exc}") from exc
        if not response.audios:
            return np.zeros(0, dtype=np.float32)

        wav_bytes = base64.b64decode(response.audios[0])
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            self.sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()

        if sample_width != 2:
            raise RuntimeError(f"Unexpected Sarvam audio sample width: {sample_width} bytes")
        audio_int16 = np.frombuffer(frames, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0


class EdgeTTSSynthesizer(Synthesizer):
    """Free, no API key, genuine Azure Neural voice quality — via the same
    backend Edge browser's "Read Aloud" feature uses. Unofficial/reverse
    engineered (not a public Microsoft API), so it can in principle be
    rate-limited or broken without notice, though it's been stable for the
    community for years. Covers English, Hindi, and Telugu with real named
    neural voices — configurable per language in .env.example."""

    def __init__(
        self,
        voice_en: str | None = None,
        voice_hi: str | None = None,
        voice_te: str | None = None,
    ) -> None:
        self._voices = {
            "en": voice_en or config.EDGE_TTS_VOICE_EN,
            "hi": voice_hi or config.EDGE_TTS_VOICE_HI,
            "te": voice_te or config.EDGE_TTS_VOICE_TE,
        }
        self.sample_rate = 24_000  # updated from the actual decoded audio per call

    def synthesize(self, text: str, language: str | None = None) -> np.ndarray:
        import edge_tts
        import soundfile as sf

        voice = self._voices.get(language or "en", self._voices["en"])

        async def _stream() -> bytes:
            chunks = []
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            mp3_bytes = asyncio.run(_stream())
        except Exception as exc:
            raise RuntimeError(f"Could not reach Edge TTS: {exc}") from exc
        if not mp3_bytes:
            return np.zeros(0, dtype=np.float32)

        audio, sample_rate = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        self.sample_rate = sample_rate
        return audio
