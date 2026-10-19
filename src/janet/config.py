"""Centralized environment loading.

Import this before reading any env var used elsewhere in Janet — it loads
.env exactly once as a side effect.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # no-op if .env is absent

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "piper")
PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_v3")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_SPEAKER = os.getenv("SARVAM_SPEAKER", "priya")
SARVAM_MODEL = os.getenv("SARVAM_MODEL", "bulbul:v3")

EDGE_TTS_VOICE_EN = os.getenv("EDGE_TTS_VOICE_EN", "en-US-JennyNeural")
EDGE_TTS_VOICE_HI = os.getenv("EDGE_TTS_VOICE_HI", "hi-IN-SwaraNeural")
EDGE_TTS_VOICE_TE = os.getenv("EDGE_TTS_VOICE_TE", "te-IN-ShrutiNeural")

# If the primary TTS_PROVIDER fails (e.g. quota exhausted, or edge_tts gets
# rate-limited), fall back to this one for the rest of the session. Set to
# empty to disable and fail hard instead.
TTS_FALLBACK_PROVIDER = os.getenv("TTS_FALLBACK_PROVIDER", "piper")

WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL")

MEMORY_FILE = os.getenv("MEMORY_FILE", "data/memory.json")

RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
RAG_DIR = os.getenv("RAG_DIR", "data/rag")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
RAG_RECALL_K = int(os.getenv("RAG_RECALL_K", "4"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.6"))
INBOX_DIR = os.getenv("INBOX_DIR", "data/inbox")
UPLOAD_MAX_MB = int(os.getenv("UPLOAD_MAX_MB", "25"))

UI_ENABLED = os.getenv("UI_ENABLED", "true").lower() == "true"
UI_PORT = int(os.getenv("UI_PORT", "8765"))
