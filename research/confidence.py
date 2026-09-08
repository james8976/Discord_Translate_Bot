import numpy as np
from typing import List, Tuple, Any

def entropy_confidence(distances: np.ndarray) -> float:
    """
    基于距离分布的熵计算置信度。
    距离越集中在最近邻，熵越小，置信度越高。
    
    Args:
        distances (np.ndarray): 候选词到目标向量的距离数组。
        
    Returns:
        float: 返回 [0, 1] 之间的置信度分数。
    """
    # 将距离转换为类似概率的分布（距离越小概率越大）
    weights = np.exp(-distances)
    probs = weights / np.sum(weights)
    
    # 计算信息熵
    entropy = -np.sum(probs * np.log(probs + 1e-10))
    # 最大可能熵
    max_entropy = np.log(len(distances))
    
    # 归一化并取反，使得 1 表示最高置信度
    if max_entropy == 0:
        return 1.0
    return 1.0 - (entropy / max_entropy)

class ConfidenceEstimator:
    """
    对齐置信度评估器，用于判断词汇映射的可靠性以及检测特殊用法（如俚语）。
    """
    def __init__(self, threshold: float = 0.6) -> None:
        """
        初始化评估器。
        
        Args:
            threshold (float): 高置信度阈值。
        """
        self.threshold = threshold

    def compute(self, similarities: np.ndarray) -> float:
        """
        计算单次映射的置信度。
        
        Args:
            similarities (np.ndarray): 目标词与候选词组的余弦相似度。
            
        Returns:
            float: 置信度得分。
        """
        # 距离可定义为 1 - 相似度
        distances = 1.0 - similarities
        return entropy_confidence(distances)

    def classify(self, confidence: float) -> str:
        """
        根据置信度得分对映射结果进行分类。
        
        Args:
            confidence (float): 置信度得分。
            
        Returns:
            str: 'High' 或 'Low'。
        """
        if confidence >= self.threshold:
            return "High"
        return "Low"

    def is_likely_slang(self, src_confidence: float, tgt_confidence: float) -> bool:
        """
        启发式判断是否可能为俚语。
        如果源语言空间内上下文置信度高，但目标语言映射置信度极低，可能是独有俚语。
        
        Args:
            src_confidence (float): 源语言上下文的确定性。
            tgt_confidence (float): 跨语言映射的置信度。
            
        Returns:
            bool: 是否为俚语候选。
        """
        return src_confidence > 0.8 and tgt_confidence < 0.3
