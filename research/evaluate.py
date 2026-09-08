import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict

def precision_at_k(predictions: List[List[str]], ground_truth: List[str], k: int) -> float:
    """
    计算 Precision@K 指标。
    
    Args:
        predictions (List[List[str]]): 预测的 top-N 候选词列表的列表。
        ground_truth (List[str]): 对应的真实目标词列表。
        k (int): K 值，如 1, 5, 10。
        
    Returns:
        float: Precision@K 的比例。
    """
    correct = 0
    for preds, truth in zip(predictions, ground_truth):
        # 截取 top-k
        top_k = preds[:k]
        if truth in top_k:
            correct += 1
    
    if not predictions:
        return 0.0
    return correct / len(predictions)

def hubness_analysis(neighbors_list: List[List[str]]) -> Dict[str, int]:
    """
    分析“中心性”(Hubness) 问题。
    计算目标语言中每个词成为源语言词汇近邻的频率。
    
    Args:
        neighbors_list (List[List[str]]): 为每个查询词找出的近邻列表（通常 k=1 或 k=5）。
        
    Returns:
        Dict[str, int]: 每个目标词作为近邻被命中的次数。
    """
    hub_counts: Dict[str, int] = defaultdict(int)
    for neighbors in neighbors_list:
        for word in neighbors:
            hub_counts[word] += 1
    return dict(hub_counts)

def compare_metrics(metrics1: Dict[str, float], metrics2: Dict[str, float]) -> Dict[str, float]:
    """
    比较两次不同实验的评估指标，计算绝对提升。
    
    Args:
        metrics1 (Dict[str, float]): 基线指标。
        metrics2 (Dict[str, float]): 实验指标。
        
    Returns:
        Dict[str, float]: 指标差值 (metrics2 - metrics1)。
    """
    diff = {}
    all_keys = set(metrics1.keys()).union(set(metrics2.keys()))
    for key in all_keys:
        val1 = metrics1.get(key, 0.0)
        val2 = metrics2.get(key, 0.0)
        diff[key] = val2 - val1
    return diff
