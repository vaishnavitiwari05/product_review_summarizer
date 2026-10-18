"""Phase 6: text embedders used to group similar opinions.

  * SentenceTransformerEmbedder - semantic (paraphrases land close together)
  * TfidfEmbedder               - lexical fallback, no download, fitted on the texts given

Both return L2-normalised numpy arrays so cosine similarity == dot product.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

log = logging.getLogger(__name__)
_NEGATIONS = {"not", "no", "nor", "never", "cannot", "without"}


class Embedder(ABC):
    name = "base"
    # cosine-DISTANCE below which two opinions count as "the same opinion"
    distance_threshold = 0.5

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray: ...


class TfidfEmbedder(Embedder):
    name = "tfidf"
    distance_threshold = 0.85

    def embed(self, texts: list[str]) -> np.ndarray:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
        stop = sorted(set(ENGLISH_STOP_WORDS) - _NEGATIONS)     # keep negations: "not great" != "great"
        vec = TfidfVectorizer(stop_words=stop, ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        try:
            x = vec.fit_transform(texts)
        except ValueError:                                       # only stop words
            return np.zeros((len(texts), 1))
        return np.asarray(x.todense())  # already L2-normalised by TfidfVectorizer


class SentenceTransformerEmbedder(Embedder):
    name = "sbert"
    distance_threshold = 0.45

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False))


def get_embedder(backend: str | None = None, model: str | None = None) -> Embedder:
    from app.utils.config import settings
    from app.utils.errors import DataValidationError
    backend = (backend or settings.embedding_backend).lower()
    if backend == "tfidf":
        return TfidfEmbedder()
    if backend in ("sbert", "auto"):
        try:
            return SentenceTransformerEmbedder(model or settings.embedding_model)
        except Exception as exc:
            if backend == "sbert":
                raise DataValidationError(
                    "embedding_model_unavailable",
                    "The sentence-embedding model could not be loaded. Check your internet connection "
                    "and that 'sentence-transformers' is installed, or set EMBEDDING_BACKEND=tfidf.",
                    status_code=503, details={"reason": str(exc)[:200]})
            log.warning("Sentence embeddings unavailable (%s); falling back to TF-IDF.", exc)
            return TfidfEmbedder()
    raise ValueError(f"Unknown EMBEDDING_BACKEND '{backend}'")
