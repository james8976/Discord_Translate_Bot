# -*- coding: utf-8 -*-
"""
PongPong Bot — 圖表模組
使用 matplotlib 產生深色主題的價格走勢圖，回傳 BytesIO
"""

import io
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import matplotlib
matplotlib.use('Agg')  # 無 GUI 後端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from utils.logger import get_logger

logger = get_logger('chart')

# ── 深色主題設定 ───────────────────────────────────────────
DARK_BG = '#2C2F33'
DARKER_BG = '#23272A'
TEXT_COLOR = '#FFFFFF'
GRID_COLOR = '#40444B'
LINE_COLOR_UP = '#57F287'
LINE_COLOR_DOWN = '#ED4245'
LINE_COLOR_DEFAULT = '#5865F2'


def _apply_dark_style(ax: plt.Axes, fig: plt.Figure) -> None:
    """套用深色主題樣式"""
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARKER_BG)
    ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(GRID_COLOR)
    ax.spines['bottom'].set_color(GRID_COLOR)
    ax.grid(True, color=GRID_COLOR, alpha=0.3, linestyle='--')


async def generate_stock_chart(
    symbol: str,
    dates: list,
    prices: list[float],
    title: str,
    currency_symbol: str = '$'
) -> io.BytesIO:
    """
    產生股票/加密貨幣走勢圖。

    Parameters
    ----------
    symbol : str       股票代碼
    dates : list       日期列表
    prices : list      收盤價列表
    title : str        圖表標題
    currency_symbol : str  貨幣符號（如 $ ¥ NT$）

    Returns
    -------
    io.BytesIO  PNG 圖檔
    """
    def _render():
        fig, ax = plt.subplots(figsize=(10, 5))
        _apply_dark_style(ax, fig)

        # 判斷漲跌顏色
        if len(prices) >= 2:
            color = LINE_COLOR_UP if prices[-1] >= prices[0] else LINE_COLOR_DOWN
        else:
            color = LINE_COLOR_DEFAULT

        # 繪製走勢線
        ax.plot(dates, prices, color=color, linewidth=2, alpha=0.9)

        # 填充面積
        ax.fill_between(dates, prices, min(prices) * 0.99, alpha=0.1, color=color)

        # 標注最高 / 最低點
        if prices:
            max_idx = prices.index(max(prices))
            min_idx = prices.index(min(prices))
            ax.annotate(
                f'▲ {currency_symbol}{prices[max_idx]:,.2f}',
                xy=(dates[max_idx], prices[max_idx]),
                fontsize=8, color=LINE_COLOR_UP, fontweight='bold',
                textcoords='offset points', xytext=(0, 10),
                ha='center'
            )
            ax.annotate(
                f'▼ {currency_symbol}{prices[min_idx]:,.2f}',
                xy=(dates[min_idx], prices[min_idx]),
                fontsize=8, color=LINE_COLOR_DOWN, fontweight='bold',
                textcoords='offset points', xytext=(0, -15),
                ha='center'
            )

        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_ylabel(f'Price ({currency_symbol})', fontsize=10)

        # 日期格式
        if len(dates) > 60:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        fig.autofmt_xdate(rotation=30)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf

    try:
        return await asyncio.to_thread(_render)
    except Exception as e:
        logger.error(f'圖表產生失敗 ({symbol}): {e}')
        raise


async def generate_currency_chart(
    from_cur: str,
    to_cur: str,
    dates: list,
    rates: list[float],
) -> io.BytesIO:
    """
    產生匯率走勢圖。

    Parameters
    ----------
    from_cur / to_cur : str   貨幣代碼
    dates : list              日期
    rates : list[float]       匯率

    Returns
    -------
    io.BytesIO  PNG 圖檔
    """
    title = f'{from_cur.upper()} → {to_cur.upper()} 匯率走勢'

    def _render():
        fig, ax = plt.subplots(figsize=(10, 5))
        _apply_dark_style(ax, fig)

        color = LINE_COLOR_DEFAULT
        ax.plot(dates, rates, color=color, linewidth=2, alpha=0.9)
        ax.fill_between(dates, rates, min(rates) * 0.99, alpha=0.1, color=color)

        if rates:
            max_idx = rates.index(max(rates))
            min_idx = rates.index(min(rates))
            ax.annotate(
                f'▲ {rates[max_idx]:,.4f}',
                xy=(dates[max_idx], rates[max_idx]),
                fontsize=8, color=LINE_COLOR_UP, fontweight='bold',
                textcoords='offset points', xytext=(0, 10), ha='center'
            )
            ax.annotate(
                f'▼ {rates[min_idx]:,.4f}',
                xy=(dates[min_idx], rates[min_idx]),
                fontsize=8, color=LINE_COLOR_DOWN, fontweight='bold',
                textcoords='offset points', xytext=(0, -15), ha='center'
            )

        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_ylabel('Rate', fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        fig.autofmt_xdate(rotation=30)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf

    try:
        return await asyncio.to_thread(_render)
    except Exception as e:
        logger.error(f'匯率圖表產生失敗 ({from_cur}->{to_cur}): {e}')
        raise
