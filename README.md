# Janet

Janet is a voice-first, multi-agent assistant. It listens for a wake word,
transcribes speech locally, routes the request through a LangGraph
multi-agent orchestrator (with RAG and tool-calling), speaks the response,
and — eventually — animates a Live2D avatar while it does it.

## Architecture (planned)

```
 mic audio
   │
   ▼
[stt]  wake-word detection ──▶ local speech-to-text
   │
   ▼
[agents]  LangGraph orchestrator
   ├── retrieves context via [rag]
   ├── calls tools (scheduler jobs, external APIs, ...)
   └── produces a response
   │
   ▼
[tts]  text-to-speech
   │
   ▼
avatar frontend (Live2D) — speaks + animates
```

`[eval]` runs offline against recorded/synthetic conversations to score
agent responses and catch regressions. `[scheduler]` handles recurring
and background jobs (reminders, periodic checks) that can trigger the
agent outside of a live conversation.

The avatar/voice-loop frontend is not built yet. The plan is to fork
[Open-LLM-VTuber](https://github.com/t41372/Open-LLM-VTuber) and adapt its
Live2D rendering and voice-loop layer to sit on top of `src/janet` instead
of implementing that layer from scratch. See `frontend/README.md`.

## Project layout

```
janet/
├── src/janet/
│   ├── stt/         wake-word detection + local speech-to-text
│   ├── tts/         text-to-speech
│   ├── agents/      LangGraph orchestrator, tool-calling agents
│   ├── rag/         retrieval-augmented generation (ingest, index, retrieve)
│   ├── eval/        eval loop for scoring agent behavior
│   └── scheduler/   recurring/background job scheduling
├── frontend/        placeholder for the future Open-LLM-VTuber fork
├── pyproject.toml
├── .env.example
└── .gitignore
```

## Status

This is a bare scaffold: package structure and project metadata only, no
dependencies installed and no implementation yet.

## Setup

1. Create/activate a virtualenv (Python 3.11+):
   ```
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # macOS/Linux
   ```
2. Install the project in editable mode once dependencies are added:
   ```
   pip install -e .
   ```
3. Copy the env template and fill in your keys:
   ```
   cp .env.example .env
   ```
   - `GROQ_API_KEY` — Groq API access (LLM inference)
   - `GOOGLE_API_KEY` — Google API access (LLM/other Google services)

   Never commit `.env` — it's already covered by `.gitignore`.

## Roadmap

- [ ] Wake-word detection + local STT (`stt`)
- [ ] LangGraph orchestrator with tool-calling (`agents`)
- [ ] RAG ingestion + retrieval (`rag`)
- [ ] TTS output (`tts`)
- [ ] Eval harness (`eval`)
- [ ] Job scheduler (`scheduler`)
- [ ] Fork Open-LLM-VTuber for the Live2D avatar + voice-loop frontend
