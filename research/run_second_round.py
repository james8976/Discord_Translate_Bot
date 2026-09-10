"""Second-round experiment: pivot anchors, CSLS retrieval, and optional LLM review.

The direct Japanese-Chinese dictionary is reserved for evaluation. Training
anchors are generated only from the training splits of Chinese-English and
English-Japanese dictionaries, preventing pivot-induced test leakage.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import html
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research.align import CrossLingualAligner
from research.config import ALL_LANGS, DATA_DIR, RUNS_DIR
from research.embeddings import EmbeddingSpace, load_fasttext_vectors
from research.llm_judge import OpenAIJudge
from research.pivot import (
    build_zh_ja_pivot,
    deterministic_split,
    filter_to_vocab,
    remove_held_out_pairs,
    reverse_pairs,
)
from research.retrieval import CSLSRetriever


WordPair = Tuple[str, str]


def load_dictionary(path: str) -> List[WordPair]:
    """Load a whitespace-delimited bilingual dictionary."""
    pairs: List[WordPair] = []
    with open(path, 'r', encoding='utf-8') as dictionary:
        for line in dictionary:
            fields = line.strip().split()
            if len(fields) >= 2:
                pairs.append((fields[0], fields[1]))
    return pairs


def load_special_dictionary(path: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """Load the fixed standard-word and slang blind test sets."""
    groups: Dict[str, List[Tuple[str, str, str]]] = {'standard': [], 'special': []}
    with open(path, 'r', encoding='utf-8') as dictionary:
        for line in dictionary:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) < 4:
                continue
            source, target, category, description = fields[:4]
            groups['standard' if category == 'standard' else 'special'].append(
                (source, target, description),
            )
    return groups


def build_matrices(
    pairs: Iterable[WordPair], source_space: EmbeddingSpace, target_space: EmbeddingSpace,
) -> Tuple[np.ndarray, np.ndarray, List[WordPair]]:
    source_vectors: List[np.ndarray] = []
    target_vectors: List[np.ndarray] = []
    valid: List[WordPair] = []
    for source, target in pairs:
        if source in source_space.word2vec and target in target_space.word2vec:
            source_vectors.append(source_space[source])
            target_vectors.append(target_space[target])
            valid.append((source, target))
    if not valid:
        return np.empty((0, 0)), np.empty((0, 0)), []
    return np.asarray(source_vectors), np.asarray(target_vectors), valid


def top_neighbors(
    aligner: CrossLingualAligner,
    source_space: EmbeddingSpace,
    target_space: EmbeddingSpace,
    source_word: str,
    count: int,
    retriever: Optional[CSLSRetriever],
) -> List[Tuple[str, float]]:
    mapped = aligner.translate_word(source_space[source_word])
    if retriever is not None:
        return retriever.nearest_neighbors(mapped, count)
    return target_space.nearest_neighbors(mapped, count)


def confidence_from_margin(scores: Sequence[float], temperature: float = 0.05) -> float:
    """Return a bounded top-1/top-2 confidence feature for later calibration."""
    if len(scores) < 2:
        return 1.0
    margin = float(scores[0] - scores[1])
    return float(1 / (1 + np.exp(-np.clip(margin / temperature, -60, 60))))


def evaluate(
    aligner: CrossLingualAligner,
    pairs: Iterable[WordPair],
    source_space: EmbeddingSpace,
    target_space: EmbeddingSpace,
    retriever: Optional[CSLSRetriever],
    descriptions: Optional[Dict[WordPair, str]] = None,
    ks: Sequence[int] = (1, 5, 10),
) -> Tuple[Dict[int, float], List[Dict[str, Any]]]:
    """Evaluate P@K plus candidates and a margin confidence feature."""
    hits = {k: 0 for k in ks}
    total = 0
    details: List[Dict[str, Any]] = []
    for source, expected in pairs:
        if source not in source_space.word2vec or expected not in target_space.word2vec:
            continue
        neighbors = top_neighbors(
            aligner, source_space, target_space, source, max(ks), retriever,
        )
        words = [word for word, _ in neighbors]
        scores = [score for _, score in neighbors]
        total += 1
        for k in ks:
            hits[k] += int(expected in words[:k])
        details.append({
            'source': source,
            'expected': expected,
            'predicted': words[0],
            'top5': words[:5],
            'top5_scores': scores[:5],
            'found_at': words.index(expected) + 1 if expected in words else -1,
            'correct': words[0] == expected,
            'margin_confidence': confidence_from_margin(scores),
            'description': descriptions.get((source, expected), '') if descriptions else '',
        })
    return {k: (hits[k] / total * 100 if total else 0.0) for k in ks}, details


def hubness_skewness(details: Iterable[Dict[str, Any]]) -> Tuple[float, Dict[str, int]]:
    """Measure how often a target term occurs in the returned top-five lists."""
    counts: Dict[str, int] = {}
    for detail in details:
        for target in detail['top5']:
            counts[target] = counts.get(target, 0) + 1
    values = np.asarray(list(counts.values()), dtype=np.float32)
    if len(values) < 2:
        return 0.0, counts
    mean = values.mean()
    return float(np.mean(((values - mean) / (values.std() + 1e-10)) ** 3)), counts


def load_embeddings(max_words: int) -> Dict[str, EmbeddingSpace]:
    """Load the FastText vocabularies used by second-round experiments."""
    embeddings: Dict[str, EmbeddingSpace] = {}
    for language in ALL_LANGS:
        path = os.path.join(DATA_DIR, f'wiki.{language}.vec')
        if not os.path.exists(path):
            raise FileNotFoundError(
                f'Missing {path}. Run research/run_experiment.py without --skip-download first.',
            )
        embeddings[language] = EmbeddingSpace(load_fasttext_vectors(path, max_words=max_words))
        print(f'  Loaded {language}: {len(embeddings[language].words):,} words')
    return embeddings


def prepare_pivot_sets(
    embeddings: Dict[str, EmbeddingSpace], seed: int,
) -> Tuple[Dict[str, List[WordPair]], Dict[str, Any], Dict[str, List[WordPair]]]:
    """Create filtered pivot training sets and independent direct held-out tests."""
    zh_en = load_dictionary(os.path.join(DATA_DIR, 'zh-en.txt'))
    en_ja = load_dictionary(os.path.join(DATA_DIR, 'en-ja.txt'))
    ja_zh = load_dictionary(os.path.join(DATA_DIR, 'ja-zh.txt'))

    zh_en_train, _ = deterministic_split(zh_en, seed=seed)
    en_ja_train, _ = deterministic_split(en_ja, seed=seed + 1)
    _, ja_zh_test = deterministic_split(ja_zh, seed=seed + 2)

    pivot_zh_ja, stats = build_zh_ja_pivot(zh_en_train, en_ja_train)
    pivot_zh_ja = filter_to_vocab(
        pivot_zh_ja, set(embeddings['zh'].words), set(embeddings['ja'].words),
    )
    pivot_ja_zh = filter_to_vocab(
        reverse_pairs(pivot_zh_ja), set(embeddings['ja'].words), set(embeddings['zh'].words),
    )
    zh_ja_test = reverse_pairs(ja_zh_test)
    pivot_zh_ja = remove_held_out_pairs(pivot_zh_ja, zh_ja_test)
    pivot_ja_zh = remove_held_out_pairs(pivot_ja_zh, ja_zh_test)

    metadata = asdict(stats)
    metadata.update({
        'pivot_after_vocab_filter': len(pivot_zh_ja),
        'direct_ja_zh_held_out': len(ja_zh_test),
        'seed': seed,
    })
    return {'zh-ja': pivot_zh_ja, 'ja-zh': pivot_ja_zh}, metadata, {
        'zh-ja': zh_ja_test,
        'ja-zh': ja_zh_test,
    }


def write_pairs(path: str, pairs: Iterable[WordPair]) -> None:
    with open(path, 'w', encoding='utf-8', newline='\n') as output:
        for source, target in pairs:
            output.write(f'{source}\t{target}\n')


def write_html_report(path: str, result: Dict[str, Any]) -> None:
    """Write a local report without exposing API credentials."""
    rows = []
    for method, metrics in result['methods'].items():
        precision = metrics['precision_test']
        rows.append(
            '<tr><td>{}</td><td>{:.1f}%</td><td>{:.1f}%</td><td>{:.1f}%</td><td>{:.2f}</td></tr>'.format(
                html.escape(method), precision['1'], precision['5'], precision['10'], metrics['hubness_skewness'],
            ),
        )
    content = """<!doctype html><html lang=\"zh-Hant\"><meta charset=\"utf-8\"><title>PongPong 第二輪實驗</title>
<style>body{font-family:system-ui,'Microsoft JhengHei';max-width:900px;margin:40px auto;line-height:1.65;color:#20242c}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3df;padding:10px;text-align:left}th{background:#edf2fb}.note{background:#fff5d6;padding:14px;border-left:4px solid #d69e2e}</style>
<h1>PongPong 第二輪跨語言對齊</h1><p>方向：{direction}｜有效 Pivot 訓練錨點：{anchors}｜獨立直接詞典測試：{tests}</p>
<h2>Cosine 與 CSLS 比較</h2><table><tr><th>方法</th><th>P@1</th><th>P@5</th><th>P@10</th><th>Hubness 偏度</th></tr>{rows}</table>
<h2>實驗規範</h2><p class=\"note\">Pivot 錨點僅由中英、英日詞典的訓練分割生成；直接日中詞典只作測試。LLM 標記是輔助語義評估，並非黃金標準，應以抽樣人工複核驗證。</p>
<p>Run ID: {run_id}</p></html>""".format(
        direction=html.escape(result['direction']), anchors=result['pivot_training_pairs'],
        tests=result['held_out_test_pairs'], rows=''.join(rows), run_id=html.escape(result['run_id']),
    )
    with open(path, 'w', encoding='utf-8') as output:
        output.write(content)


def run_direction(
    direction: str,
    train_pairs: List[WordPair],
    test_pairs: List[WordPair],
    embeddings: Dict[str, EmbeddingSpace],
    methods: Sequence[str],
    csls_k: int,
    csls_reference_size: int,
    special_path: Optional[str],
    judge: Optional[OpenAIJudge],
    llm_max_items: int,
    output_dir: str,
) -> Dict[str, Any]:
    """Train one direction once, then evaluate Cosine and/or CSLS retrieval."""
    source_language, target_language = direction.split('-')
    source_space = embeddings[source_language]
    target_space = embeddings[target_language]
    source_matrix, target_matrix, valid_train = build_matrices(train_pairs, source_space, target_space)
    if len(valid_train) < 300:
        raise RuntimeError(f'{direction} has only {len(valid_train)} valid anchors; need at least 300')

    aligner = CrossLingualAligner()
    aligner.train(source_matrix, target_matrix, normalize=True)
    aligner.save(os.path.join(output_dir, f'W_pivot_{direction}.pkl'))
    mapped_train = aligner.translate_word(source_matrix)

    special_groups: Dict[str, List[Tuple[str, str, str]]] = {}
    if special_path and os.path.exists(special_path) and direction == 'ja-zh':
        special_groups = load_special_dictionary(special_path)

    result: Dict[str, Any] = {
        'direction': direction,
        'pivot_training_pairs': len(valid_train),
        'held_out_test_pairs': len(test_pairs),
        'methods': {},
    }
    for method in methods:
        retriever = None
        if method == 'csls':
            retriever = CSLSRetriever(
                target_space, mapped_train, k=csls_k, max_reference_vectors=csls_reference_size,
            )
        precision, details = evaluate(aligner, test_pairs, source_space, target_space, retriever)
        skewness, _ = hubness_skewness(details)
        method_result: Dict[str, Any] = {
            'precision_test': {str(key): value for key, value in precision.items()},
            'hubness_skewness': skewness,
            'test_details': details,
        }
        for group_name, group_rows in special_groups.items():
            group_pairs = [(source, target) for source, target, _ in group_rows]
            descriptions = {(source, target): desc for source, target, desc in group_rows}
            group_precision, group_details = evaluate(
                aligner, group_pairs, source_space, target_space, retriever, descriptions,
            )
            method_result[f'precision_{group_name}'] = {
                str(key): value for key, value in group_precision.items()
            }
            method_result[f'{group_name}_details'] = group_details

        if judge is not None and method == 'csls' and 'special_details' in method_result:
            rows = [
                {'index': index, 'source': item['source'], 'expected': item['expected'], 'predicted': item['predicted']}
                for index, item in enumerate(method_result['special_details'])
            ]
            method_result['llm_special_judgements'] = judge.judge(
                rows,
                'Judge whether the predicted Chinese translation is semantically equivalent to the expected translation for this Japanese social-language term.',
                llm_max_items,
            )
        result['methods'][method] = method_result
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='PongPong 第二輪：Pivot + CSLS + optional LLM judge')
    parser.add_argument('--skip-download', action='store_true', help='Require existing FastText and dictionaries')
    parser.add_argument('--small', action='store_true', help='Use FastText top 50K vocabulary')
    parser.add_argument('--max-words', type=int, default=200000)
    parser.add_argument('--direction', choices=['ja-zh', 'zh-ja'], default='ja-zh')
    parser.add_argument('--method', choices=['cosine', 'csls', 'both'], default='both')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--csls-k', type=int, default=10)
    parser.add_argument('--csls-reference-size', type=int, default=2000)
    parser.add_argument('--llm-judge', action='store_true', help='Explicitly send bounded term rows to OpenAI')
    parser.add_argument('--llm-model', default=os.getenv('OPENAI_MODEL', ''))
    parser.add_argument('--llm-max-items', type=int, default=40)
    args = parser.parse_args()

    if not args.skip_download:
        from research.run_experiment import download_all_data
        download_all_data(False)
    max_words = 50000 if args.small else args.max_words
    methods = ['cosine', 'csls'] if args.method == 'both' else [args.method]
    run_id = time.strftime('%Y-%m-%d_%H%M%S')
    output_dir = os.path.join(RUNS_DIR, run_id, 'second_round', args.direction)
    os.makedirs(output_dir, exist_ok=True)

    print(f'Loading embeddings (top {max_words:,} words)...')
    embeddings = load_embeddings(max_words)
    pivot_sets, pivot_metadata, test_sets = prepare_pivot_sets(embeddings, args.seed)
    write_pairs(os.path.join(output_dir, 'pivot_zh_ja_train.tsv'), pivot_sets['zh-ja'])
    write_pairs(os.path.join(output_dir, 'pivot_ja_zh_train.tsv'), pivot_sets['ja-zh'])

    judge = None
    if args.llm_judge:
        judge = OpenAIJudge(args.llm_model, os.getenv('OPENAI_API_KEY', ''))
        print(f'LLM semantic review enabled for at most {args.llm_max_items} terms.')

    result = run_direction(
        args.direction, pivot_sets[args.direction], test_sets[args.direction], embeddings, methods,
        args.csls_k, args.csls_reference_size, os.path.join(DATA_DIR, 'slang_pairs_ja_zh.tsv'),
        judge, args.llm_max_items, output_dir,
    )
    result.update({'run_id': run_id, 'pivot_metadata': pivot_metadata, 'max_words': max_words})
    with open(os.path.join(output_dir, 'results.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    write_html_report(os.path.join(output_dir, 'report.html'), result)
    print(f'Finished: {output_dir}')


if __name__ == '__main__':
    main()
