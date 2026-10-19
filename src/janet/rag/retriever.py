"""The interface the rest of Janet uses for RAG: recall context for a turn,
search on demand (as a tool), and save memories/conversation turns.

Every method here fails soft — an embedding outage or a missing key logs a
warning and returns nothing, so RAG can never break the voice loop."""

import threading
from datetime import datetime

from janet import config
from janet.rag.embedder import Embedder
from janet.rag.store import SearchResult, VectorStore

_KIND_LABELS = {"document": "From the user's files", "memory": "Remembered fact", "conversation": "Past conversation"}


def _format(results: list[SearchResult]) -> str:
    lines = []
    for r in results:
        rec = r["record"]
        date = rec["created_at"][:10]
        lines.append(f"- ({_KIND_LABELS.get(rec['kind'], rec['kind'])}, {date}) {rec['text']}")
    return "\n".join(lines)


class Retriever:
    def __init__(self) -> None:
        self.store = VectorStore()
        self.embedder = Embedder()

    def recall(self, query: str, exclude_texts: set[str] | None = None) -> str | None:
        """Passive recall run before every turn: only close matches, so
        unrelated small talk doesn't drag random memories into the prompt."""
        try:
            results = self.store.search(
                self.embedder.embed_query(query),
                k=config.RAG_RECALL_K,
                min_score=config.RAG_MIN_SCORE,
                exclude_texts=exclude_texts,
            )
        except Exception as exc:
            print(f"[rag] recall failed: {exc}")
            return None
        return _format(results) if results else None

    def search(self, query: str, kinds: set[str] | None = None, k: int = 5) -> str:
        """Active search the model asks for via a tool — looser threshold, more results."""
        try:
            results = self.store.search(self.embedder.embed_query(query), k=k, kinds=kinds, min_score=0.45)
        except Exception as exc:
            return f"Knowledge search failed: {exc}"
        return _format(results) if results else "Nothing relevant found in the knowledge base."

    def _add(self, text: str, kind: str) -> None:
        try:
            self.store.add([text], self.embedder.embed_documents([text]), kind=kind, source=kind, created_at=datetime.now().isoformat())
        except Exception as exc:
            print(f"[rag] failed to save {kind}: {exc}")

    def add_memory(self, fact: str) -> None:
        self._add(fact, "memory")

    def sync_memories(self, facts: list[str]) -> None:
        """Indexes any memory.json facts not yet in the store (e.g. ones saved before RAG existed)."""
        indexed = self.store.texts("memory")
        missing = [f for f in facts if f not in indexed]
        if not missing:
            return
        try:
            self.store.add(missing, self.embedder.embed_documents(missing), kind="memory", source="memory", created_at=datetime.now().isoformat())
        except Exception as exc:
            print(f"[rag] failed to index existing memories: {exc}")

    def add_conversation_turn(self, user_text: str, reply: str) -> None:
        """Saved off the critical path so the embedding call doesn't delay Janet's spoken reply."""
        threading.Thread(target=self._add, args=(f"User said: {user_text}\nJanet replied: {reply}", "conversation"), daemon=True).start()


_instance: Retriever | None = None
_init_failed = False


def get_retriever() -> Retriever | None:
    """Lazily builds the shared Retriever. Returns None if RAG is disabled or
    couldn't start (e.g. no GOOGLE_API_KEY), after warning once."""
    global _instance, _init_failed
    if not config.RAG_ENABLED or _init_failed:
        return None
    if _instance is None:
        try:
            _instance = Retriever()
        except Exception as exc:
            print(f"[rag] disabled: {exc}")
            _init_failed = True
            return None
    return _instance
