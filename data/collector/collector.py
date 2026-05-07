"""AKShare 数据采集"""
import time
from datetime import date, datetime
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from config.settings import AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY, DEFAULT_START_DATE


class StockCollector:
    """A股数据采集器"""

    def _retry(self, func, *args, **kwargs):
        """带重试的 API 调用"""
        for attempt in range(1, AKSHARE_RETRY_COUNT + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"API 调用失败 (第{attempt}次): {e}")
                if attempt < AKSHARE_RETRY_COUNT:
                    time.sleep(AKSHARE_RETRY_DELAY * attempt)
                else:
                    logger.error(f"API 调用彻底失败: {func.__name__}")
                    raise

    def get_stock_list(self) -> pd.DataFrame:
        """获取 A股股票列表"""
        logger.info("获取股票列表...")
        df = self._retry(ak.stock_info_a_code_name)
        result = df.rename(columns={"code": "code", "name": "name"})
        result = result[["code", "name"]].copy()
        result["industry"] = ""
        result["list_date"] = ""
        logger.info(f"获取到 {len(result)} 只股票")
        return result

    def get_stock_daily(
        self,
        code: str,
        start_date: str = DEFAULT_START_DATE,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """获取单只股票日K线数据"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.debug(f"[{code}] 采集日K: {start_date} ~ {end_date}")
        df = self._retry(
            ak.stock_zh_a_hist,
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )

        if df.empty:
            return pd.DataFrame()

        result = df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
        )
        result = result[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
        result["date"] = pd.to_datetime(result["date"])
        return result

    def get_batch_daily(
        self,
        codes: list[str],
        start_date: str = DEFAULT_START_DATE,
        end_date: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        """批量采集多只股票日K线"""
        results = {}
        total = len(codes)
        for i, code in enumerate(codes, 1):
            logger.info(f"[{i}/{total}] 采集 {code}")
            try:
                df = self.get_stock_daily(code, start_date, end_date)
                results[code] = df
                time.sleep(0.5)  # 避免请求过快
            except Exception as e:
                logger.error(f"[{code}] 采集失败: {e}")
                results[code] = pd.DataFrame()
        return results

    def get_index_daily(
        self,
        code: str,
        start_date: str = DEFAULT_START_DATE,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """获取指数日K线数据"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.debug(f"[{code}] 采集指数日K: {start_date} ~ {end_date}")
        try:
            df = self._retry(
                ak.stock_zh_index_daily,
                symbol=code,
            )
        except Exception:
            # 备用接口
            df = self._retry(
                ak.index_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
            )

        if df.empty:
            return pd.DataFrame()

        # 统一列名
        col_map = {
            "日期": "date", "date": "date",
            "开盘": "open", "open": "open",
            "最高": "high", "high": "high",
            "最低": "low", "low": "low",
            "收盘": "close", "close": "close",
            "成交量": "volume", "volume": "volume",
            "成交额": "amount", "amount": "amount",
        }
        df = df.rename(columns=col_map)
        cols = ["date", "open", "high", "low", "close", "volume", "amount"]
        df = df[[c for c in cols if c in df.columns]].copy()
        df["date"] = pd.to_datetime(df["date"])
        if "volume" not in df.columns:
            df["volume"] = 0
        if "amount" not in df.columns:
            df["amount"] = 0
        # 筛选日期范围
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
        return df
