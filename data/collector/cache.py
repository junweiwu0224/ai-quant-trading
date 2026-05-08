"""通用 TTL 缓存（线程安全，LRU 淘汰）"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Entry:
    expire_at: float
    value: Any


class TTLCache:
    """带 TTL 和 LRU 淘汰的内存缓存

    - 每次 get/set 计数，满 50 次自动清理过期条目
    - 超过 max_size 时淘汰最旧条目
    """

    def __init__(self, max_size: int = 500):
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._ops = 0

    def get(self, key: str) -> tuple[bool, Any]:
        """读缓存，返回 (hit, value)"""
        with self._lock:
            entry = self._store.get(key)
            if entry and entry.expire_at > time.time():
                return True, entry.value
            self._store.pop(key, None)
            return False, None

    def set(self, key: str, value: Any, ttl: float):
        """写缓存，ttl 单位秒"""
        with self._lock:
            self._store[key] = _Entry(expire_at=time.time() + ttl, value=value)
            self._maybe_evict()

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def _maybe_evict(self):
        """每 50 次操作清理一次"""
        self._ops += 1
        if self._ops < 50:
            return
        self._ops = 0
        now = time.time()
        expired = [k for k, e in self._store.items() if e.expire_at <= now]
        for k in expired:
            del self._store[k]
        if len(self._store) > self._max_size:
            sorted_keys = sorted(self._store, key=lambda k: self._store[k].expire_at)
            for k in sorted_keys[: len(self._store) - self._max_size]:
                del self._store[k]
