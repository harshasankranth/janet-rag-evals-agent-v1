"""Live document intake while Janet is running: anything that lands in
INBOX_DIR — dragged onto the HUD (see ui.server's /upload) or copied there by
hand — is indexed in the background, and Janet is told it arrived so she can
answer "summarise the PDF I just sent"."""

import json
import threading
import time
from pathlib import Path
from typing import Callable

from janet import config
from janet.rag.ingest import PDF_SUFFIXES, TEXT_SUFFIXES, ingest_file
from janet.rag.retriever import Retriever

SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES
_POLL_SECONDS = 2.0


class InboxWatcher:
    def __init__(self, retriever: Retriever, emit: Callable[[dict], None], directory: str = config.INBOX_DIR) -> None:
        self._retriever = retriever
        self._emit = emit
        self._dir = Path(directory)
        # Remembers each file's mtime at its last ingest, so restarts don't re-embed everything.
        self._manifest_path = Path(config.RAG_DIR) / "inbox_manifest.json"
        self._manifest: dict[str, float] = self._load_manifest()
        self._recent: list[str] = []  # names ingested this session, newest last
        self._lock = threading.Lock()

    def _load_manifest(self) -> dict[str, float]:
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_manifest(self) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(self._manifest, indent=2), encoding="utf-8")

    def recent_documents(self) -> list[str]:
        with self._lock:
            return list(self._recent)

    def start(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            try:
                self._scan()
            except Exception as exc:
                print(f"[inbox] scan failed: {exc}")
            time.sleep(_POLL_SECONDS)

    def _scan(self) -> None:
        for path in sorted(self._dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            key = str(path.resolve())
            mtime = path.stat().st_mtime
            if self._manifest.get(key) == mtime:
                continue
            if time.time() - mtime < _POLL_SECONDS:
                continue  # probably still being written/copied; pick it up next scan
            self._ingest(path, key, mtime)

    def _ingest(self, path: Path, key: str, mtime: float) -> None:
        self._emit({"type": "document", "status": "indexing", "name": path.name})
        print(f"[inbox] indexing {path.name}...")
        try:
            chunks = ingest_file(path, self._retriever.store, self._retriever.embedder)
        except Exception as exc:
            print(f"[inbox] failed to index {path.name}: {exc}")
            self._emit({"type": "document", "status": "error", "name": path.name, "error": str(exc)})
            self._manifest[key] = mtime  # don't retry a broken file every 2 seconds
            self._save_manifest()
            return
        self._manifest[key] = mtime
        self._save_manifest()
        with self._lock:
            if path.name in self._recent:
                self._recent.remove(path.name)
            self._recent.append(path.name)
        print(f"[inbox] indexed {path.name} ({chunks} chunks)")
        self._emit({"type": "document", "status": "ready", "name": path.name, "chunks": chunks})
