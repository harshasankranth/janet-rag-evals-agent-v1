"""A small persistent vector store: one numpy matrix of unit vectors plus a
parallel JSON list of records, saved under RAG_DIR.

Brute-force cosine search over a numpy matrix is effectively instant at a
personal assistant's scale (tens of thousands of chunks), and avoids pulling
in a vector database dependency. Swap this module out if that ever changes."""

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, TypedDict

import numpy as np

from janet import config


class Record(TypedDict):
    id: str
    kind: str  # "document" | "memory" | "conversation"
    text: str
    source: str  # file path for documents, "memory"/"conversation" otherwise
    created_at: str  # ISO timestamp


class SearchResult(TypedDict):
    record: Record
    score: float


class VectorStore:
    def __init__(self, directory: str = config.RAG_DIR, dim: int = config.EMBEDDING_DIM) -> None:
        self._dir = Path(directory)
        self._vectors_path = self._dir / "vectors.npy"
        self._records_path = self._dir / "records.json"
        self._dim = dim
        self._lock = threading.Lock()  # conversation turns are saved from a background thread
        self._records: list[Record] = []
        self._vectors = np.zeros((0, dim), dtype=np.float32)
        self._load()

    def _load(self) -> None:
        if not (self._vectors_path.exists() and self._records_path.exists()):
            return
        vectors = np.load(self._vectors_path)
        records = json.loads(self._records_path.read_text(encoding="utf-8"))
        if vectors.shape[0] != len(records) or (len(records) and vectors.shape[1] != self._dim):
            raise RuntimeError(
                f"RAG index at {self._dir} is inconsistent or was built with a different "
                "EMBEDDING_DIM. Delete that folder and re-run `janet-ingest` to rebuild it."
            )
        self._vectors, self._records = vectors.astype(np.float32), records

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        # Write to temp files then rename, so a crash mid-save can't corrupt the index.
        tmp_vectors = self._vectors_path.with_suffix(".tmp.npy")
        tmp_records = self._records_path.with_suffix(".tmp")
        np.save(tmp_vectors, self._vectors)
        tmp_records.write_text(json.dumps(self._records, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_vectors, self._vectors_path)
        os.replace(tmp_records, self._records_path)

    def __len__(self) -> int:
        return len(self._records)

    def add(self, texts: list[str], vectors: np.ndarray, kind: str, source: str, created_at: str) -> None:
        if not texts:
            return
        new_records: list[Record] = [
            {"id": uuid.uuid4().hex, "kind": kind, "text": t, "source": source, "created_at": created_at}
            for t in texts
        ]
        with self._lock:
            self._records.extend(new_records)
            self._vectors = np.vstack([self._vectors, vectors.astype(np.float32)])
            self._save()

    def delete_source(self, source: str) -> int:
        """Removes every record from `source` (used to re-ingest a changed file). Returns the count removed."""
        with self._lock:
            keep = [i for i, r in enumerate(self._records) if r["source"] != source]
            removed = len(self._records) - len(keep)
            if removed:
                self._records = [self._records[i] for i in keep]
                self._vectors = self._vectors[keep]
                self._save()
            return removed

    def texts(self, kind: str) -> set[str]:
        return {r["text"] for r in self._records if r["kind"] == kind}

    def sources(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._records:
            if r["kind"] == "document":
                counts[r["source"]] = counts.get(r["source"], 0) + 1
        return counts

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 4,
        kinds: set[str] | None = None,
        min_score: float = 0.0,
        exclude_texts: set[str] | None = None,
    ) -> list[SearchResult]:
        with self._lock:
            if not self._records:
                return []
            scores = self._vectors @ query_vector
            order = np.argsort(-scores)
            results: list[SearchResult] = []
            for i in order:
                score = float(scores[i])
                if score < min_score:
                    break  # sorted descending, nothing further will pass
                record = self._records[i]
                if kinds and record["kind"] not in kinds:
                    continue
                if exclude_texts and record["text"] in exclude_texts:
                    continue
                results.append({"record": record, "score": score})
                if len(results) >= k:
                    break
            return results

    def stats(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for r in self._records:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        return {"total": len(self._records), "by_kind": counts, "directory": str(self._dir)}
