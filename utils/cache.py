# -*- coding: utf-8 -*-
"""
PongPong Bot — 快取模組
基於 dict 的 TTL 快取，使用 asyncio.Lock 確保執行緒安全
"""

import time
import asyncio
from typing import Any


class TTLCache:
    """簡單的 TTL (Time-To-Live) 快取"""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def is_expired(self, key: str) -> bool:
        """檢查指定 key 是否已過期"""
        if key not in self._store:
            return True
        _, expire_at = self._store[key]
        return time.time() > expire_at

    async def get(self, key: str) -> Any | None:
        """取得快取值，過期或不存在則回傳 None"""
        async with self._lock:
            if key not in self._store:
                return None
            value, expire_at = self._store[key]
            if time.time() > expire_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """設定快取值"""
        async with self._lock:
            ttl = ttl if ttl is not None else self._default_ttl
            self._store[key] = (value, time.time() + ttl)

    async def clear(self) -> None:
        """清除所有快取"""
        async with self._lock:
            self._store.clear()

    async def cleanup(self) -> int:
        """清除所有過期項目，回傳清除數量"""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)
