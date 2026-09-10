"""Build high-precision Chinese-Japanese anchors through an English pivot.

The module intentionally keeps only one-to-one English entries.  This is more
conservative than taking every Cartesian-product match, but it avoids adding
unlabelled polysemy to the Procrustes training set.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import random
from typing import Dict, Iterable, List, Sequence, Set, Tuple


WordPair = Tuple[str, str]


@dataclass(frozen=True)
class PivotBuildStats:
    """Audit information for a pivot build, stored with each experiment."""

    zh_en_input: int
    en_ja_input: int
    shared_english: int
    ambiguous_english: int
    one_to_one_english: int
    output_pairs: int


def normalize_english(word: str) -> str:
    """Return a stable join key without changing the stored surface forms."""
    return " ".join(word.casefold().strip().split())


def deterministic_split(
    pairs: Sequence[WordPair], train_ratio: float = 0.8, seed: int = 42,
) -> Tuple[List[WordPair], List[WordPair]]:
    """Split a dictionary once, before any pivot join, to prevent leakage."""
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    shuffled = list(pairs)
    random.Random(seed).shuffle(shuffled)
    split_at = int(len(shuffled) * train_ratio)
    return shuffled[:split_at], shuffled[split_at:]


def build_zh_ja_pivot(
    zh_en_pairs: Iterable[WordPair], en_ja_pairs: Iterable[WordPair],
) -> Tuple[List[WordPair], PivotBuildStats]:
    """Join ``zh -> en`` and ``en -> ja`` dictionaries into ``zh -> ja`` pairs.

    Only one-to-one English keys are retained.  An English lemma that maps to
    multiple entries in either dictionary is counted as ambiguous and excluded
    rather than silently selecting an arbitrary translation.
    """
    zh_by_en: Dict[str, Set[str]] = defaultdict(set)
    ja_by_en: Dict[str, Set[str]] = defaultdict(set)
    zh_en_count = 0
    en_ja_count = 0

    for zh, en in zh_en_pairs:
        key = normalize_english(en)
        if key:
            zh_by_en[key].add(zh.strip())
            zh_en_count += 1

    for en, ja in en_ja_pairs:
        key = normalize_english(en)
        if key:
            ja_by_en[key].add(ja.strip())
            en_ja_count += 1

    shared = set(zh_by_en).intersection(ja_by_en)
    ambiguous = 0
    output: Set[WordPair] = set()
    for english in shared:
        zh_words = zh_by_en[english]
        ja_words = ja_by_en[english]
        if len(zh_words) != 1 or len(ja_words) != 1:
            ambiguous += 1
            continue
        output.add((next(iter(zh_words)), next(iter(ja_words))))

    pairs = sorted(output)
    stats = PivotBuildStats(
        zh_en_input=zh_en_count,
        en_ja_input=en_ja_count,
        shared_english=len(shared),
        ambiguous_english=ambiguous,
        one_to_one_english=len(shared) - ambiguous,
        output_pairs=len(pairs),
    )
    return pairs, stats


def filter_to_vocab(
    pairs: Iterable[WordPair], source_vocab: Set[str], target_vocab: Set[str],
) -> List[WordPair]:
    """Keep pairs whose two surface forms are available to the embedding model."""
    return [(src, tgt) for src, tgt in pairs if src in source_vocab and tgt in target_vocab]


def reverse_pairs(pairs: Iterable[WordPair]) -> List[WordPair]:
    """Reverse a bilingual dictionary while deduplicating its entries."""
    return sorted({(target, source) for source, target in pairs})


def remove_held_out_pairs(pairs: Iterable[WordPair], held_out: Iterable[WordPair]) -> List[WordPair]:
    """Remove evaluation pairs from a generated training set exactly."""
    held_out_set = set(held_out)
    return [(source, target) for source, target in pairs if (source, target) not in held_out_set]
