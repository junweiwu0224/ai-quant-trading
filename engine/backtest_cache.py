"""回测结果缓存模块

解决 backtest.py 中多个分析端点重复运行回测的问题。
使用 LRU 策略 + TTL 过期机制缓存回测结果。
"""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass(frozen=True)
class CacheEntry:
    """缓存条目"""
    timestamp: float
    data: dict


class BacktestCache:
    """回测结果缓存

    特性：
    - LRU 淘汰策略（最近最少使用）
    - TTL 自动过期（默认 5 分钟）
    - 线程安全（threading.Lock 保护共享状态）
    """

    def __init__(self, max_size: int = 20, ttl_seconds: int = 300):
        """初始化缓存

        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def _make_key(self, params: dict) -> str:
        """基于回测参数生成缓存 key

        使用稳定的 JSON 序列化 + MD5 哈希。
        """
        # 过滤掉不可哈希的参数
        stable_params = {}
        for k, v in sorted(params.items()):
            if isinstance(v, (list, tuple)):
                stable_params[k] = tuple(v) if isinstance(v, list) else v
            else:
                stable_params[k] = v

        stable_json = json.dumps(stable_params, sort_keys=True, default=str)
        return hashlib.md5(stable_json.encode()).hexdigest()

    def get(self, params: dict) -> Optional[dict]:
        """获取缓存结果

        Args:
            params: 回测参数

        Returns:
            缓存的回测结果，如果未命中或已过期则返回 None
        """
        key = self._make_key(params)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # 检查是否过期
            if time.time() - entry.timestamp > self._ttl:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"缓存已过期: {key[:8]}...")
                return None

            # LRU: 移到末尾（最近使用）
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"缓存命中: {key[:8]}...")
            return entry.data

    def set(self, params: dict, data: dict):
        """设置缓存

        Args:
            params: 回测参数
            data: 回测结果
        """
        key = self._make_key(params)

        with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                del self._cache[key]
            # 如果缓存已满，淘汰最旧的
            elif len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"缓存淘汰: {evicted_key[:8]}...")

            self._cache[key] = CacheEntry(
                timestamp=time.time(),
                data=data
            )
            logger.debug(f"缓存设置: {key[:8]}...")

    def get_or_run(self, params: dict, run_fn) -> dict:
        """获取缓存或运行回测（线程安全，防止重复计算）

        Args:
            params: 回测参数
            run_fn: 运行回测的函数（无参数，返回 dict）

        Returns:
            回测结果
        """
        # 尝试从缓存获取
        cached = self.get(params)
        if cached is not None:
            return cached

        # 缓存未命中，加锁防止并发重复计算
        with self._lock:
            # 双重检查：其他线程可能已填充
            key = self._make_key(params)
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry.timestamp <= self._ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return entry.data

            # 运行回测（持锁期间，其他线程等待）
            result = run_fn()

            # 缓存结果
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"缓存淘汰: {evicted_key[:8]}...")

            self._cache[key] = CacheEntry(
                timestamp=time.time(),
                data=result,
            )
            return result

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.debug("缓存已清空")

    def stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "ttl_seconds": self._ttl,
            }


# 全局缓存实例（线程安全双重检查锁）
_backtest_cache: Optional[BacktestCache] = None
_cache_init_lock = threading.Lock()


def get_backtest_cache() -> BacktestCache:
    """获取全局回测缓存实例（线程安全）"""
    global _backtest_cache
    if _backtest_cache is None:
        with _cache_init_lock:
            if _backtest_cache is None:
                _backtest_cache = BacktestCache(max_size=20, ttl_seconds=300)
    return _backtest_cache


def clear_backtest_cache():
    """清空全局回测缓存"""
    cache = get_backtest_cache()
    cache.clear()
