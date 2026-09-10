"""Cosine and CSLS retrieval for cross-lingual word alignment."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from research.embeddings import EmbeddingSpace


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize a vector or a batch without modifying the caller's array."""
    values = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return values / norms


def _top_mean(values: np.ndarray, k: int) -> float:
    k = min(k, values.size)
    if k == 0:
        return 0.0
    return float(np.partition(values, values.size - k)[-k:].mean())


class CSLSRetriever:
    """Retrieve target words with Cross-domain Similarity Local Scaling.

    ``reference_sources`` should be mapped source-language training anchors.
    A deterministic cap keeps the computation practical for a 200K FastText
    vocabulary while retaining an auditable sample of the training space.
    """

    def __init__(
        self,
        target_space: EmbeddingSpace,
        reference_sources: np.ndarray,
        k: int = 10,
        max_reference_vectors: int = 2000,
        chunk_size: int = 2048,
    ) -> None:
        if k < 1:
            raise ValueError("CSLS k must be positive")
        if reference_sources.size == 0:
            raise ValueError("CSLS requires at least one mapped source anchor")

        self.target_space = target_space
        self.k = k
        reference = normalize_rows(reference_sources)
        if len(reference) > max_reference_vectors:
            indices = np.linspace(0, len(reference) - 1, max_reference_vectors, dtype=int)
            reference = reference[indices]
        self.reference_size = len(reference)
        self.target_penalty = self._build_target_penalty(reference, chunk_size)

    def _build_target_penalty(self, reference: np.ndarray, chunk_size: int) -> np.ndarray:
        penalties = np.empty(len(self.target_space.words), dtype=np.float32)
        for start in range(0, len(self.target_space.words), chunk_size):
            end = min(start + chunk_size, len(self.target_space.words))
            similarities = self.target_space.matrix[start:end] @ reference.T
            k = min(self.k, similarities.shape[1])
            penalties[start:end] = np.partition(
                similarities, similarities.shape[1] - k, axis=1,
            )[:, -k:].mean(axis=1)
        return penalties

    def nearest_neighbors(self, vector: np.ndarray, k: int = 5) -> List[Tuple[str, float]]:
        query = normalize_rows(vector)
        similarities = self.target_space.matrix @ query
        source_penalty = _top_mean(similarities, self.k)
        scores = 2 * similarities - source_penalty - self.target_penalty
        count = min(k, len(scores))
        indices = np.argpartition(scores, len(scores) - count)[-count:]
        indices = indices[np.argsort(scores[indices])[::-1]]
        return [(self.target_space.words[i], float(scores[i])) for i in indices]
