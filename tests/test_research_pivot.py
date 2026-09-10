import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research.pivot import build_zh_ja_pivot, deterministic_split, filter_to_vocab, remove_held_out_pairs
from research.retrieval import CSLSRetriever
from research.embeddings import EmbeddingSpace


def test_pivot_keeps_only_one_to_one_english_keys():
    zh_en = [("貓", "cat"), ("狗", "dog"), ("犬", "dog")]
    en_ja = [("CAT", "猫"), ("dog", "犬")]

    pairs, stats = build_zh_ja_pivot(zh_en, en_ja)

    assert pairs == [("貓", "猫")]
    assert stats.shared_english == 2
    assert stats.ambiguous_english == 1


def test_pivot_split_is_reproducible_and_filters_held_out_pairs():
    pairs = [(str(index), str(index)) for index in range(10)]
    train_a, test_a = deterministic_split(pairs, seed=9)
    train_b, test_b = deterministic_split(pairs, seed=9)

    assert (train_a, test_a) == (train_b, test_b)
    assert len(train_a) == 8
    assert remove_held_out_pairs(train_a, train_a[:2]) == train_a[2:]
    assert filter_to_vocab(train_a, {pair[0] for pair in train_a}, {pair[1] for pair in train_a}) == train_a


def test_csls_retrieves_expected_target_in_a_separable_space():
    target = EmbeddingSpace({
        "alpha": np.array([1.0, 0.0], dtype=np.float32),
        "beta": np.array([0.0, 1.0], dtype=np.float32),
        "noise": np.array([-1.0, 0.0], dtype=np.float32),
    })
    retriever = CSLSRetriever(target, np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32), k=1)

    assert retriever.nearest_neighbors(np.array([1.0, 0.0], dtype=np.float32), k=1)[0][0] == "alpha"
