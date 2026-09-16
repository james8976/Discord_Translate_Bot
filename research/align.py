import numpy as np
from scipy.linalg import svd
import pickle
from typing import Optional


def _normalize_rows(values: np.ndarray) -> np.ndarray:
    """L2-normalize a vector or row matrix without mutating the input."""
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return values / norms


def procrustes_align(
    X_src: np.ndarray,
    Y_tgt: np.ndarray,
    mean_center: bool = False,
) -> tuple:
    """Compute the optimal orthogonal rotation matrix W via Procrustes alignment.

    Minimises  ||X_src @ W - Y_tgt||_F  subject to  W^T W = I.

    Improvement 1 — Mean Centering:
        When mean_center is True, the per-language centroid is subtracted
        from each anchor matrix before the SVD.  This removes the geometric
        bias caused by high-frequency function words (e.g. Chinese stopwords
        like 'que' / 'yu') that cluster near the centroid of their embedding
        space.  The centroids are returned so that query vectors can be
        centred identically at inference time.

    Args:
        X_src: Source-language anchor matrix, shape (n, d).
        Y_tgt: Target-language anchor matrix, shape (n, d).
        mean_center: If True, subtract per-language mean before SVD.

    Returns:
        Tuple of (W, src_mean, tgt_mean).
        W        -- optimal rotation matrix, shape (d, d).
        src_mean -- source centroid; zeros when mean_center=False, shape (d,).
        tgt_mean -- target centroid; zeros when mean_center=False, shape (d,).
    """
    src_mean = np.zeros(X_src.shape[1], dtype=X_src.dtype)
    tgt_mean = np.zeros(Y_tgt.shape[1], dtype=Y_tgt.dtype)

    if mean_center:
        src_mean = X_src.mean(axis=0)
        tgt_mean = Y_tgt.mean(axis=0)
        X_src = X_src - src_mean
        Y_tgt = Y_tgt - tgt_mean

    # SVD of the cross-covariance matrix: M = X^T Y = U Sigma V^T
    # Optimal W* = U V^T  (maximises Tr(W^T M))
    M = X_src.T @ Y_tgt
    U, _, Vt = svd(M)
    W = U @ Vt
    return W, src_mean, tgt_mean


class CrossLingualAligner:
    """Manage the orthogonal rotation that maps one language space to another.

    Supports two training modes (controlled by normalize and mean_center):
      - normalize=True   : L2-normalise anchors before SVD (original behaviour).
      - mean_center=True : subtract per-language centroid before SVD (Round-3 default).

    Both modes may be combined.
    """

    def __init__(self) -> None:
        """Initialise with no rotation matrix."""
        self.W: Optional[np.ndarray] = None
        self.normalize_input: bool = False
        self.mean_center: bool = False
        self.src_mean: Optional[np.ndarray] = None
        self.tgt_mean: Optional[np.ndarray] = None

    def train(
        self,
        X_src: np.ndarray,
        Y_tgt: np.ndarray,
        normalize: bool = False,
        mean_center: bool = False,
    ) -> None:
        """Compute and store the rotation matrix from aligned anchor pairs.

        Args:
            X_src: Source anchor vectors, shape (n, d).
            Y_tgt: Target anchor vectors, shape (n, d).
            normalize: L2-normalise anchors before SVD.
            mean_center: Subtract per-language mean before SVD (Improvement 1).
        """
        self.normalize_input = normalize
        self.mean_center = mean_center
        if normalize:
            X_src = _normalize_rows(X_src)
            Y_tgt = _normalize_rows(Y_tgt)
        self.W, self.src_mean, self.tgt_mean = procrustes_align(
            X_src, Y_tgt, mean_center=mean_center
        )

    def translate_word(self, vec: np.ndarray) -> np.ndarray:
        """Map a source-language vector into the target-language space.

        When mean centering is active, the stored source centroid is subtracted
        before rotation to match the coordinate frame used during training.

        Args:
            vec: Source vector(s), shape (d,) or (n, d).

        Returns:
            Mapped vector(s) in the target space.

        Raises:
            ValueError: If the aligner has not been trained yet.
        """
        if self.W is None:
            raise ValueError("Aligner has not been trained. Call train() first.")
        if self.normalize_input:
            vec = _normalize_rows(vec)
        if self.mean_center and self.src_mean is not None:
            vec = vec - self.src_mean
        return vec @ self.W

    def save(self, path: str) -> None:
        """Serialise the rotation matrix and centroids to path.

        Args:
            path: Destination file path.
        """
        if self.W is None:
            raise ValueError("No rotation matrix to save.")
        payload = {
            'W': self.W,
            'src_mean': self.src_mean,
            'tgt_mean': self.tgt_mean,
            'normalize_input': self.normalize_input,
            'mean_center': self.mean_center,
        }
        with open(path, 'wb') as f:
            pickle.dump(payload, f)

    def load(self, path: str) -> None:
        """Restore a previously saved aligner from path.

        Supports both the legacy format (bare ndarray) and the new dict format.

        Args:
            path: Source file path.
        """
        with open(path, 'rb') as f:
            payload = pickle.load(f)
        if isinstance(payload, dict):
            self.W = payload['W']
            self.src_mean = payload.get('src_mean')
            self.tgt_mean = payload.get('tgt_mean')
            self.normalize_input = payload.get('normalize_input', False)
            self.mean_center = payload.get('mean_center', False)
        else:
            # Legacy: raw ndarray saved directly
            self.W = payload
            self.src_mean = None
            self.tgt_mean = None

