import math
import numpy as np
from typing import Optional


# Default embedding dimension used to derive the temperature default.
_DEFAULT_DIM = 300


def entropy_confidence(
    distances: np.ndarray,
    temperature: Optional[float] = None,
    dim: int = _DEFAULT_DIM,
) -> float:
    """Compute a normalised Shannon-entropy confidence score from top-K distances.

    Improvement 2 — Temperature Scaling:
        In high-dimensional spaces (d >= 300), raw L2/cosine distances tend to
        concentrate, causing the naive Softmax distribution to collapse to one-hot
        extremes (either 0.0 or 1.0) with almost no useful gradient in between.
        A temperature tau = 1 / sqrt(d) is applied before exponentiation:

            p_i = exp(-d_i / tau) / sum_j exp(-d_j / tau)

        This smooths the probability distribution so that confidence scores span
        the full [0, 1] range rather than snapping to the boundary values.

    Args:
        distances: Array of top-K cosine distances (1 - similarity), shape (K,).
        temperature: Softmax temperature tau.  Defaults to 1 / sqrt(dim).
        dim: Embedding dimensionality used to derive the default tau.

    Returns:
        Confidence score in [0, 1].  1.0 = maximally confident; 0.0 = geometric
        collapse (uniform probability — hub attraction or slang OOV).
    """
    if temperature is None:
        temperature = 1.0 / math.sqrt(dim)

    # Temperature-scaled Softmax: distances -> probability
    scaled = -distances / temperature
    scaled -= scaled.max()          # numerical stability
    weights = np.exp(scaled)
    probs = weights / weights.sum()

    # Shannon entropy H(p) = -sum p_i log p_i
    entropy = -float(np.sum(probs * np.log(probs + 1e-12)))
    max_entropy = math.log(len(distances))

    if max_entropy == 0.0:
        return 1.0
    # Normalised confidence: 1 when distribution is peaked, 0 when uniform
    return float(1.0 - entropy / max_entropy)


class ConfidenceEstimator:
    """Evaluate alignment confidence and detect slang / OOV via entropy.

    Parameters
    ----------
    threshold:
        Boundary between 'High' and 'Low' confidence classifications.
    temperature:
        Softmax temperature for entropy_confidence.  None uses 1/sqrt(dim).
    dim:
        Embedding dimension; used only when temperature is None.
    """

    def __init__(
        self,
        threshold: float = 0.6,
        temperature: Optional[float] = None,
        dim: int = _DEFAULT_DIM,
    ) -> None:
        self.threshold = threshold
        self.temperature = temperature
        self.dim = dim

    def compute(self, similarities: np.ndarray) -> float:
        """Return the confidence score for one mapping.

        Args:
            similarities: Cosine similarities to the top-K target candidates,
                          shape (K,).  Higher = closer.

        Returns:
            Confidence in [0, 1].
        """
        distances = 1.0 - similarities
        return entropy_confidence(distances, temperature=self.temperature, dim=self.dim)

    def classify(self, confidence: float) -> str:
        """Classify a confidence score as 'High' or 'Low'.

        Args:
            confidence: Score from compute().

        Returns:
            'High' if confidence >= threshold, else 'Low'.
        """
        return "High" if confidence >= self.threshold else "Low"

    def is_likely_slang(self, src_confidence: float, tgt_confidence: float) -> bool:
        """Heuristic: flag as potential slang when source is certain but target collapses.

        A word is flagged as likely slang when the source-side context is
        well-defined (high confidence) yet the cross-lingual projection is
        highly uncertain (low confidence), indicating a lexical gap between
        the two spaces.

        Args:
            src_confidence: Confidence within the source-language space.
            tgt_confidence: Confidence of the cross-lingual mapping.

        Returns:
            True if the word is a slang / OOV candidate.
        """
        return src_confidence > 0.8 and tgt_confidence < 0.3

