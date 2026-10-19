"""Turns text into embedding vectors via Gemini's embedding model.

Kept independent of LLM_PROVIDER: the chat model can be Groq or Ollama while
embeddings still come from Gemini, since gemini-embedding-001 is multilingual
(English/Hindi/Telugu queries match documents in any of the three)."""

import numpy as np
from google import genai
from google.genai import types as gtypes

from janet import config

_BATCH_SIZE = 100  # Gemini's per-request cap on embed_content inputs


class Embedder:
    def __init__(self, model: str = config.EMBEDDING_MODEL, dim: int = config.EMBEDDING_DIM) -> None:
        if not config.GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not set — RAG needs it for Gemini embeddings.")
        self._client = genai.Client(api_key=config.GOOGLE_API_KEY)
        self._model = model
        self.dim = dim

    def _embed(self, texts: list[str], task_type: str) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            response = self._client.models.embed_content(
                model=self._model,
                contents=texts[start : start + _BATCH_SIZE],
                config=gtypes.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
            )
            vectors.extend(e.values for e in response.embeddings)
        matrix = np.asarray(vectors, dtype=np.float32)
        # Truncated (non-3072) Gemini embeddings aren't unit length; normalize so
        # a plain dot product is cosine similarity.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "RETRIEVAL_QUERY")[0]
