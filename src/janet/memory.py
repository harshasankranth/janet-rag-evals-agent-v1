"""Lightweight persistent memory: durable facts Janet has learned about the
user, stored locally as JSON and carried across sessions. Not a knowledge
base or full conversation log — just the "remembers who you are" kind of
memory a personal assistant needs. Full semantic/RAG-style memory over
whole conversations is a separate, later piece of work."""

import json
from pathlib import Path

from janet import config

_MAX_FACTS = 50


def _path() -> Path:
    return Path(config.MEMORY_FILE)


def load_facts() -> list[str]:
    path = _path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    facts = data.get("facts", []) if isinstance(data, dict) else []
    return [f for f in facts if isinstance(f, str)]


def remember(fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    facts = load_facts()
    if fact in facts:
        return
    facts.append(fact)
    facts = facts[-_MAX_FACTS:]  # simple FIFO cap so the system prompt can't grow unbounded

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"facts": facts}, indent=2, ensure_ascii=False), encoding="utf-8")
