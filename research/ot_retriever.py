"""Optimal Transport retrieval via batch Sinkhorn algorithm.

Why OT for slang/meme translation
-----------------------------------
Standard cosine retrieval treats each query independently.
CSLS penalizes local hubs but still processes queries one-by-one.

Sinkhorn OT processes ALL test queries TOGETHER as a distribution:
  - Enforces a "mass conservation" constraint across the full batch
  - If hub word X already absorbed many queries, it gets penalized globally
  - Rare slang words in isolated regions of the target space get a "fair chance"
  - Works better across typologically different language pairs without language-
    specific tuning (important for scaling to many world languages)

This file implements:
  OTRetriever : batch Sinkhorn nearest-neighbour retrieval
  sinkhorn_log: numerically stable log-domain Sinkhorn-Knopp iterations
"""
from __future__ import annotations

import numpy as np
from typing import List, Tuple


def _logsumexp(X: np.ndarray, axis: int) -> np.ndarray:
    """Numerically stable log-sum-exp along one axis."""
    X_max = X.max(axis=axis, keepdims=True)
    out = np.log(np.exp(X - X_max).sum(axis=axis, keepdims=True) + 1e-300) + X_max
    return out


def sinkhorn_log(
    C: np.ndarray,
    reg: float = 0.05,
    max_iter: int = 300,
    tol: float = 1e-7,
) -> np.ndarray:
    """Log-domain Sinkhorn-Knopp algorithm.

    Solves the entropy-regularised optimal transport problem:

        min_{T >= 0}  sum_{ij} C_ij T_ij  -  reg * H(T)
        s.t.          T 1 = a  (row marginals)
                      T^T 1 = b  (column marginals)

    with uniform marginals  a_i = 1/N,  b_j = 1/M.

    Args:
        C      : cost matrix, shape (N, M). Typically 1 - cosine_similarity.
        reg    : regularisation strength. Smaller = harder assignment (more
                 like exact matching). Larger = softer (more like cosine).
                 Recommended range: 0.01 - 0.1.
        max_iter: maximum Sinkhorn iterations.
        tol    : convergence tolerance on the dual variable u.

    Returns:
        T : transport plan, shape (N, M). Row i gives the probability mass
            distributed from source query i to all M target candidates.
            argmax_j T[i] is the best match for query i.
    """
    N, M = C.shape
    log_K = -C / reg                        # (N, M)  log of Gibbs kernel
    log_a = np.full(N, -np.log(N))          # uniform source marginal
    log_b = np.full(M, -np.log(M))          # uniform target marginal

    log_u = np.zeros(N)                     # dual variables
    for _ in range(max_iter):
        log_v = log_b - _logsumexp(log_K + log_u[:, None], axis=0).ravel()
        log_u_new = log_a - _logsumexp(log_K + log_v[None, :], axis=1).ravel()
        if np.max(np.abs(log_u_new - log_u)) < tol:
            log_u = log_u_new
            break
        log_u = log_u_new

    log_T = log_K + log_u[:, None] + log_v[None, :]
    return np.exp(log_T)


class OTRetriever:
    """Batch Sinkhorn nearest-neighbour retrieval for CLWE evaluation.

    Instead of matching each query independently (cosine / CSLS), this class
    matches ALL queries simultaneously via optimal transport, preventing hub
    words from monopolising the retrieval for every query.

    Usage
    -----
    ot = OTRetriever(target_space, k_candidates=500, reg=0.05)
    results = ot.retrieve_batch(mapped_queries, k=10)
    # results[i] = [(word, score), ...] for query i

    Parameters
    ----------
    target_space   : EmbeddingSpace for the target language.
    k_candidates   : number of cosine-top-k candidates to consider per query
                     before running Sinkhorn. Reduces cost matrix size.
    reg            : Sinkhorn regularisation (entropy weight).
    max_iter       : maximum Sinkhorn iterations.
    """

    def __init__(
        self,
        target_space,
        k_candidates: int = 500,
        reg: float = 0.05,
        max_iter: int = 300,
    ) -> None:
        self.ts = target_space
        self.words = list(target_space.words)
        # Pre-normalise target matrix for fast cosine computation
        mat = np.stack([target_space[w] for w in self.words], axis=0)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        self.mat_norm = mat / np.where(norms == 0, 1.0, norms)   # (V, d)
        self.k_candidates = min(k_candidates, len(self.words))
        self.reg = reg
        self.max_iter = max_iter

    def retrieve_batch(
        self,
        queries: np.ndarray,
        k: int = 10,
    ) -> List[List[Tuple[str, float]]]:
        """Retrieve top-k target words for each query using batch OT.

        Args:
            queries : mapped source vectors, shape (N, d). Should already be
                      in the target embedding space (after aligner.translate_word).
            k       : number of results to return per query.

        Returns:
            List of N lists, each containing (word, cosine_score) tuples.
        """
        N = queries.shape[0]
        # L2-normalise queries
        q_norms = np.linalg.norm(queries, axis=1, keepdims=True)
        q_norm = queries / np.where(q_norms == 0, 1.0, q_norms)

        # Step 1 -- cosine similarities against full target vocab (chunked)
        chunk = 512
        sims = np.zeros((N, len(self.words)), dtype=np.float32)
        for start in range(0, len(self.words), chunk):
            end = min(start + chunk, len(self.words))
            sims[:, start:end] = q_norm @ self.mat_norm[start:end].T

        # Step 2 -- build candidate pool (union of top-k_candidates per query)
        top_idx = np.argpartition(sims, -self.k_candidates, axis=1)[:, -self.k_candidates:]
        cand_idx = np.unique(top_idx.ravel())          # (M,) M <= N * k_candidates

        # Step 3 -- cost matrix on candidate pool only
        C = (1.0 - sims[:, cand_idx]).astype(np.float64)   # (N, M)

        # Step 4 -- Sinkhorn transport plan
        T = sinkhorn_log(C, reg=self.reg, max_iter=self.max_iter)

        # Step 5 -- extract top-k per query from transport mass
        results: List[List[Tuple[str, float]]] = []
        k_actual = min(k, len(cand_idx))
        for i in range(N):
            row = T[i]
            sorted_j = np.argsort(row)[::-1][:k_actual]
            nbrs = [
                (self.words[cand_idx[j]], float(sims[i, cand_idx[j]]))
                for j in sorted_j
            ]
            results.append(nbrs)
        return results
