import numpy as np
import matplotlib.pyplot as plt
from typing import List, Dict
import matplotlib

# 配置中文字体，确保中文标签正确显示
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

def set_dark_theme() -> None:
    """应用深色主题配置 (#2C2F33 背景)。"""
    plt.style.use('dark_background')
    matplotlib.rcParams['figure.facecolor'] = '#2C2F33'
    matplotlib.rcParams['axes.facecolor'] = '#2C2F33'
    matplotlib.rcParams['text.color'] = '#FFFFFF'
    matplotlib.rcParams['axes.labelcolor'] = '#FFFFFF'
    matplotlib.rcParams['xtick.color'] = '#FFFFFF'
    matplotlib.rcParams['ytick.color'] = '#FFFFFF'
    matplotlib.rcParams['grid.color'] = '#555555'

def plot_tsne_alignment(
    src_points: np.ndarray, 
    tgt_points: np.ndarray, 
    src_labels: List[str], 
    tgt_labels: List[str], 
    title: str = "跨语言词向量 t-SNE 降维映射",
    save_path: str = None
) -> None:
    """
    绘制 t-SNE 降维后的跨语言词向量对齐散点图。
    假定输入的 points 已经是 2D 坐标。
    
    Args:
        src_points (np.ndarray): 源语言词汇二维坐标。
        tgt_points (np.ndarray): 目标语言词汇二维坐标。
        src_labels (List[str]): 源语言词汇标签。
        tgt_labels (List[str]): 目标语言词汇标签。
        title (str): 图表标题。
        save_path (str, optional): 保存路径，如果不为空则保存为图片。
    """
    set_dark_theme()
    plt.figure(figsize=(10, 8))
    
    # 绘制源语言散点
    plt.scatter(src_points[:, 0], src_points[:, 1], c='#7289DA', label='源语言 (Source)', alpha=0.7)
    for i, label in enumerate(src_labels):
        plt.annotate(label, (src_points[i, 0], src_points[i, 1]), fontsize=9, alpha=0.8)
        
    # 绘制目标语言散点
    plt.scatter(tgt_points[:, 0], tgt_points[:, 1], c='#43B581', label='目标语言 (Target)', marker='^', alpha=0.7)
    for i, label in enumerate(tgt_labels):
        plt.annotate(label, (tgt_points[i, 0], tgt_points[i, 1]), fontsize=9, alpha=0.8)
        
    plt.title(title, fontsize=14)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='#2C2F33')
    plt.close()

def plot_hubness_distribution(hub_counts: Dict[str, int], top_n: int = 20, save_path: str = None) -> None:
    """
    绘制中心性 (Hubness) 分布柱状图。
    
    Args:
        hub_counts (Dict[str, int]): 各词作为近邻的次数统计。
        top_n (int): 显示频率最高的前 N 个词。
        save_path (str, optional): 保存路径。
    """
    set_dark_theme()
    sorted_hubs = sorted(hub_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    words = [x[0] for x in sorted_hubs]
    counts = [x[1] for x in sorted_hubs]
    
    plt.figure(figsize=(12, 6))
    plt.bar(words, counts, color='#F04747')
    plt.title("Hubness 现象: 最高频近邻词分布 (Top {})".format(top_n), fontsize=14)
    plt.xlabel("目标语言词汇", fontsize=12)
    plt.ylabel("成为最近邻的次数", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, facecolor='#2C2F33')
    plt.close()

def plot_confidence_histogram(confidences: List[float], save_path: str = None) -> None:
    """
    绘制对齐置信度分数直方图。
    
    Args:
        confidences (List[float]): 置信度分数列表。
        save_path (str, optional): 保存路径。
    """
    set_dark_theme()
    plt.figure(figsize=(8, 6))
    plt.hist(confidences, bins=20, color='#FAA61A', edgecolor='black', alpha=0.8)
    plt.title("跨语言对齐置信度分布", fontsize=14)
    plt.xlabel("置信度得分 (Confidence Score)", fontsize=12)
    plt.ylabel("频次 (Frequency)", fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=300, facecolor='#2C2F33')
    plt.close()
