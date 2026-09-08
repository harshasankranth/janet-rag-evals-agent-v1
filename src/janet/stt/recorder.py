"""Microphone capture with simple RMS-energy silence detection.

No wake word: recording starts once speech is detected above threshold, and
stops after a trailing period of silence (or a hard max-duration cap).
"""

from typing import Callable

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000  # required by faster-whisper
BLOCK_MS = 30
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_MS / 1000)

SILENCE_RMS_THRESHOLD = 500.0  # int16 RMS; tune per mic/room
TRAILING_SILENCE_S = 1.0
MAX_UTTERANCE_S = 15.0


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block.astype(np.float64)))))


def record_utterance(on_block: Callable[[float], None] | None = None) -> np.ndarray:
    """Blocks until the user starts speaking and then falls silent (or
    MAX_UTTERANCE_S elapses). Returns float32 mono PCM at 16kHz in [-1, 1].

    If on_block is given, it's called once per ~30ms block with a live
    amplitude level normalized to roughly [0, 1], for driving a UI."""
    trailing_silence_blocks = int(TRAILING_SILENCE_S * 1000 / BLOCK_MS)
    max_blocks = int(MAX_UTTERANCE_S * 1000 / BLOCK_MS)

    blocks: list[np.ndarray] = []
    speech_started = False
    silence_run = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK_SIZE) as stream:
        while len(blocks) < max_blocks:
            block, _overflowed = stream.read(BLOCK_SIZE)
            block = block[:, 0]
            level = _rms(block)
            if on_block:
                on_block(min(level / SILENCE_RMS_THRESHOLD / 3, 1.0))

            if not speech_started:
                if level > SILENCE_RMS_THRESHOLD:
                    speech_started = True
                    blocks.append(block)
                continue

            blocks.append(block)
            if level > SILENCE_RMS_THRESHOLD:
                silence_run = 0
            else:
                silence_run += 1
                if silence_run >= trailing_silence_blocks:
                    break

    if not blocks:
        return np.zeros(0, dtype=np.float32)

    audio_int16 = np.concatenate(blocks)
    return audio_int16.astype(np.float32) / 32768.0
