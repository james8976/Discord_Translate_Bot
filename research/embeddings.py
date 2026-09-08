import numpy as np
from typing import Dict, List, Tuple

def load_fasttext_vectors(path: str, max_words: int = 200000) -> Dict[str, np.ndarray]:
    """
    加载 FastText 词向量文件 (.vec 格式)。
    
    Args:
        path (str): 词向量文件路径。
        max_words (int): 最大加载词汇量，用于节省内存。默认 200000。
        
    Returns:
        Dict[str, np.ndarray]: 词到向量的映射字典。
    """
    vectors: Dict[str, np.ndarray] = {}
    with open(path, 'r', encoding='utf-8', newline='\n', errors='ignore') as f:
        # 第一行通常是词汇表大小和维度，可以选择性跳过
        first_line = f.readline().split()
        if len(first_line) == 2:
            pass # header
        else:
            f.seek(0)
            
        for i, line in enumerate(f):
            if i >= max_words:
                break
            tokens = line.rstrip().split(' ')
            word = tokens[0]
            # 解析向量并转换为 numpy 数组
            vec = np.array([float(x) for x in tokens[1:]], dtype=np.float32)
            vectors[word] = vec
    return vectors

class EmbeddingSpace:
    """
    词向量空间类，提供最近邻查询等便捷方法。
    """
    def __init__(self, vectors: Dict[str, np.ndarray]) -> None:
        """
        初始化向量空间。
        
        Args:
            vectors (Dict[str, np.ndarray]): 预加载的词向量字典。
        """
        self.word2vec = vectors
        self.words = list(vectors.keys())
        # 预先堆叠并归一化向量以加速余弦相似度计算
        raw_matrix = np.stack(list(vectors.values()))
        norms = np.linalg.norm(raw_matrix, axis=1, keepdims=True)
        # 避免除以 0
        norms[norms == 0] = 1.0
        self.matrix = raw_matrix / norms
        self.word2id = {w: i for i, w in enumerate(self.words)}

    def __getitem__(self, word: str) -> np.ndarray:
        """
        获取词的向量表示。
        
        Args:
            word (str): 目标词汇。
            
        Returns:
            np.ndarray: 词向量。
            
        Raises:
            KeyError: 词汇不在词表中。
        """
        return self.word2vec[word]

    def nearest_neighbors(self, vec: np.ndarray, k: int = 5) -> List[Tuple[str, float]]:
        """
        寻找给定向量的 k 个最近邻词汇（基于余弦相似度）。
        
        Args:
            vec (np.ndarray): 查询向量。
            k (int): 返回的近邻数量。默认 5。
            
        Returns:
            List[Tuple[str, float]]: 包含 (词, 相似度) 的列表。
        """
        # 归一化查询向量
        vec_norm = np.linalg.norm(vec)
        if vec_norm == 0:
            vec_norm = 1.0
        vec = vec / vec_norm
        
        # 计算余弦相似度
        similarities = self.matrix @ vec
        
        # 获取 top k 索引
        top_k_indices = np.argsort(similarities)[-k:][::-1]
        
        return [(self.words[i], float(similarities[i])) for i in top_k_indices]
