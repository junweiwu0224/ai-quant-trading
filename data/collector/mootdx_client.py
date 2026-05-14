"""mootdx 线程安全连接管理器

核心设计：
  - threading.local() 为每个工作线程维护独立的 Quotes 实例
  - 避免多线程共享 TCP Socket 导致数据串包
  - 连接异常自动重置，下次调用自动重建
  - 所有同步调用通过 run_sync() 包装为异步
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from loguru import logger

# ── 线程池（独立于 FastAPI 的事件循环）──
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="mootdx")


async def run_sync(func, *args, **kwargs):
    """将同步阻塞调用包装为异步，防止阻塞 FastAPI 事件循环"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))


class MootdxManager:
    """mootdx 连接管理器（线程安全）

    每个线程有独立的 Quotes 实例和 TCP Socket。
    """

    DEFAULT_SERVERS = [
        ("110.41.147.114", 7709),
        ("8.129.13.54", 7709),
        ("120.24.149.49", 7709),
        ("47.113.94.204", 7709),
    ]

    def __init__(self, server: tuple[str, int] | None = None):
        self._local = threading.local()
        self._default_server = server
        self._server_list: list[tuple[str, int]] = []
        self._server_idx = 0
        self._init_servers()

    def _init_servers(self):
        """初始化服务器列表"""
        # 从配置文件读取服务器列表
        try:
            import json
            from pathlib import Path
            config_path = Path.home() / ".mootdx" / "config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text())
                servers = config.get("SERVER", {}).get("HQ", [])
                self._server_list = [(s[1], s[2]) for s in servers if len(s) >= 3]
            else:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(
                    json.dumps(
                        {
                            "SERVER": {
                                "HQ": [["tdx", host, port] for host, port in self.DEFAULT_SERVERS],
                            }
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
        except Exception as e:
            logger.debug(f"mootdx 配置初始化失败，使用内置服务器列表: {e}")

        # 如果配置文件没有，使用默认服务器
        if not self._server_list:
            self._server_list = list(self.DEFAULT_SERVERS)

        if self._default_server and self._default_server not in self._server_list:
            self._server_list.insert(0, self._default_server)

    def _get_client(self):
        """获取当前线程的独立 Quotes 实例"""
        if not hasattr(self._local, "client") or self._local.client is None:
            from mootdx.quotes import Quotes
            server = self._server_list[self._server_idx % len(self._server_list)]
            try:
                self._local.client = Quotes.factory(
                    market="std", timeout=10, server=server
                )
                self._local.server = server
            except Exception as e:
                logger.warning(f"mootdx 连接失败 {server}: {e}")
                # 尝试下一个服务器
                self._server_idx = (self._server_idx + 1) % len(self._server_list)
                server = self._server_list[self._server_idx]
                self._local.client = Quotes.factory(
                    market="std", timeout=10, server=server
                )
                self._local.server = server
        return self._local.client

    def _reset_client(self):
        """当前线程连接失效时重置"""
        self._local.client = None

    def _with_retry(self, func, *args, **kwargs):
        """带重试的同步调用，失败时切换服务器"""
        for attempt in range(3):
            try:
                client = self._get_client()
                result = func(client, *args, **kwargs)
                return result
            except Exception as e:
                logger.warning(f"mootdx 调用失败 (第{attempt+1}次): {e}")
                self._reset_client()
                self._server_idx = (self._server_idx + 1) % len(self._server_list)
                if attempt == 2:
                    raise

    # ── 异步接口 ──

    async def quotes(self, symbols: list[str]) -> pd.DataFrame:
        """批量获取实时行情"""
        def _fetch():
            return self._with_retry(lambda c: c.quotes(symbol=symbols))
        return await run_sync(_fetch)

    async def bars(self, symbol: str, frequency: int = 9,
                   start: int = 0, offset: int = 800) -> pd.DataFrame:
        """获取K线数据"""
        def _fetch():
            return self._with_retry(
                lambda c: c.bars(symbol=symbol, frequency=frequency,
                                 start=start, offset=offset)
            )
        return await run_sync(_fetch)

    async def get_kline_full(self, symbol: str, frequency: int = 9,
                             total: int = 5000) -> pd.DataFrame:
        """循环获取完整K线，突破800条限制"""
        all_data = []
        for start in range(0, total, 800):
            df = await self.bars(symbol, frequency, start, 800)
            if df is None or df.empty:
                break
            all_data.append(df)
        if not all_data:
            return pd.DataFrame()
        return pd.concat(all_data, ignore_index=True)

    async def minute(self, symbol: str) -> pd.DataFrame:
        """获取当日分时数据"""
        def _fetch():
            return self._with_retry(lambda c: c.minute(symbol=symbol))
        return await run_sync(_fetch)

    async def finance(self, symbol: str) -> pd.DataFrame:
        """获取财务概况"""
        def _fetch():
            return self._with_retry(lambda c: c.finance(symbol=symbol))
        return await run_sync(_fetch)

    async def xdxr(self, symbol: str) -> pd.DataFrame:
        """获取除权除息数据"""
        def _fetch():
            return self._with_retry(lambda c: c.xdxr(symbol=symbol))
        return await run_sync(_fetch)

    async def f10(self, symbol: str, name: str | None = None) -> dict:
        """获取F10基本面数据"""
        def _fetch():
            return self._with_retry(lambda c: c.F10(symbol=symbol, name=name))
        return await run_sync(_fetch)

    async def stocks(self, market: int = 1) -> pd.DataFrame:
        """获取股票列表（market: 1=沪市, 0=深市）"""
        def _fetch():
            return self._with_retry(lambda c: c.stocks(market=market))
        return await run_sync(_fetch)

    async def get_all_stocks(self) -> pd.DataFrame:
        """获取全市场股票列表"""
        sh = await self.stocks(market=1)
        sz = await self.stocks(market=0)
        dfs = []
        if sh is not None and not sh.empty:
            dfs.append(sh)
        if sz is not None and not sz.empty:
            dfs.append(sz)
        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)


# ── 全局单例 ──
_mootdx_manager: MootdxManager | None = None
_manager_lock = threading.Lock()


def get_mootdx_manager() -> MootdxManager:
    """获取全局 mootdx 管理器单例"""
    global _mootdx_manager
    with _manager_lock:
        if _mootdx_manager is None:
            _mootdx_manager = MootdxManager()
        return _mootdx_manager
