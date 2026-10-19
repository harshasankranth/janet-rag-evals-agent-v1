"""Retrieval-augmented generation: ingestion, indexing, and retrieval.

Three kinds of records share one index (see rag.store): documents the user
ingests with `janet-ingest`, facts saved via remember_fact, and past
conversation turns. Use `get_retriever()` from rag.retriever to access it."""
