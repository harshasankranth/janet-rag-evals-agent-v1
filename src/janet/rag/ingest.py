"""Loads files from disk, splits them into overlapping chunks, embeds them,
and adds them to the vector store. Also exposed as the `janet-ingest` CLI:

    janet-ingest notes/ lease.pdf     # index files or whole folders
    janet-ingest --list               # show what's indexed
    janet-ingest --remove lease.pdf   # drop a file from the index
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from janet.rag.embedder import Embedder
from janet.rag.store import VectorStore

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".toml"}
PDF_SUFFIXES = {".pdf"}

_CHUNK_CHARS = 700
_OVERLAP_CHARS = 120


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Reading PDFs needs pypdf: pip install -e .[rag]") from exc
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_text(text: str, size: int = _CHUNK_CHARS, overlap: int = _OVERLAP_CHARS) -> list[str]:
    """Packs paragraphs into ~`size`-char chunks, carrying the last `overlap`
    chars into the next chunk so a fact split across a boundary is still
    retrievable. Oversized paragraphs are hard-split."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paragraphs:
        while len(p) > size:
            pieces.append(p[:size])
            p = p[size - overlap :]
        pieces.append(p)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > size:
            chunks.append(current)
            current = current[-overlap:] + "\n\n" + piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def iter_files(paths: list[Path]) -> list[Path]:
    supported = TEXT_SUFFIXES | PDF_SUFFIXES
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.is_file() and p.suffix.lower() in supported)
        elif path.is_file():
            files.append(path)
        else:
            print(f"[skip] {path} does not exist")
    return files


def ingest_file(path: Path, store: VectorStore, embedder: Embedder) -> int:
    """(Re)indexes one file, replacing any chunks from a previous ingest of it. Returns the chunk count."""
    source = str(path.resolve())
    text = read_file(path)
    # Prefix each chunk with the file name so retrieval (and the model) knows where it came from.
    chunks = [f"[{path.name}]\n{c}" for c in chunk_text(text)]
    store.delete_source(source)
    if not chunks:
        return 0
    store.add(chunks, embedder.embed_documents(chunks), kind="document", source=source, created_at=datetime.now().isoformat())
    return len(chunks)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="janet-ingest", description="Index files into Janet's knowledge base.")
    parser.add_argument("paths", nargs="*", type=Path, help="files or folders to index")
    parser.add_argument("--list", action="store_true", help="list indexed documents")
    parser.add_argument("--remove", nargs="+", type=Path, metavar="PATH", help="remove files from the index")
    args = parser.parse_args()

    store = VectorStore()
    if args.list:
        for source, count in sorted(store.sources().items()):
            print(f"{count:5d} chunks  {source}")
        print(store.stats())
        return
    if args.remove:
        for path in args.remove:
            print(f"removed {store.delete_source(str(path.resolve()))} chunks from {path}")
        return
    if not args.paths:
        parser.print_help()
        return

    embedder = Embedder()
    for path in iter_files(args.paths):
        try:
            print(f"indexed {ingest_file(path, store, embedder):4d} chunks  {path}")
        except Exception as exc:
            print(f"[error] {path}: {exc}")
    print(store.stats())


if __name__ == "__main__":
    main()
