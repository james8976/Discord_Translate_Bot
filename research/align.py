import numpy as np
from scipy.linalg import svd
import pickle
from typing import Dict, Tuple, Optional

def procrustes_align(X_src: np.ndarray, Y_tgt: np.ndarray) -> np.ndarray:
    """
    计算正交 Procrustes 对齐的旋转矩阵 W。
    通过最小化 ||WX_src - Y_tgt||_F 使得源语言向量映射到目标语言向量空间。
    
    Args:
        X_src (np.ndarray): 源语言词向量矩阵，形状为 (n, d)。
        Y_tgt (np.ndarray): 目标语言词向量矩阵，形状为 (n, d)。
        
    Returns:
        np.ndarray: 最优正交旋转矩阵 W，形状为 (d, d)。
    """
    # ── 數學推導 ──
    # 目標：min ||X_src @ W - Y_tgt||_F  s.t. W^T W = I
    # 令 M = X_src^T @ Y_tgt，做 SVD：M = U Σ V^T
    # 最優解：W* = U @ V^T
    M = X_src.T @ Y_tgt
    U, _, Vt = svd(M)
    W = U @ Vt
    return W

class CrossLingualAligner:
    """
    跨语言对齐器，管理词向量的正交变换。
    """
    def __init__(self) -> None:
        """初始化对齐器，旋转矩阵初始为空。"""
        self.W: Optional[np.ndarray] = None

    def train(self, X_src: np.ndarray, Y_tgt: np.ndarray) -> None:
        """
        训练对齐器，计算并保存旋转矩阵。
        
        Args:
            X_src (np.ndarray): 源语言锚点词向量。
            Y_tgt (np.ndarray): 目标语言锚点词向量。
        """
        self.W = procrustes_align(X_src, Y_tgt)

    def translate_word(self, vec: np.ndarray) -> np.ndarray:
        """
        将源语言词向量映射到目标语言空间。
        
        Args:
            vec (np.ndarray): 源语言词向量，形状为 (d,) 或 (n, d)。
            
        Returns:
            np.ndarray: 映射后的目标语言词向量。
            
        Raises:
            ValueError: 若对齐器尚未训练。
        """
        if self.W is None:
            raise ValueError("对齐器尚未训练，请先调用 train 方法。")
        return vec @ self.W

    def save(self, path: str) -> None:
        """
        保存旋转矩阵到文件。
        
        Args:
            path (str): 保存路径。
        """
        if self.W is None:
            raise ValueError("没有可保存的旋转矩阵。")
        with open(path, 'wb') as f:
            pickle.dump(self.W, f)

    def load(self, path: str) -> None:
        """
        从文件加载旋转矩阵。
        
        Args:
            path (str): 文件路径。
        """
        with open(path, 'rb') as f:
            self.W = pickle.load(f)
