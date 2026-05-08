"""北京时间工具 — 统一项目内所有时间获取"""
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing() -> datetime:
    """返回北京时间（UTC+8），带时区信息"""
    return datetime.now(tz=BEIJING_TZ)


def now_beijing_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """返回北京时间格式化字符串"""
    return now_beijing().strftime(fmt)


def now_beijing_iso() -> str:
    """返回北京时间 ISO 8601 字符串（含 +08:00）"""
    return now_beijing().isoformat()


def today_beijing() -> str:
    """返回北京时间日期字符串 YYYY-MM-DD"""
    return now_beijing().strftime("%Y-%m-%d")


def today_beijing_compact() -> str:
    """返回北京时间日期字符串 YYYYMMDD"""
    return now_beijing().strftime("%Y%m%d")
