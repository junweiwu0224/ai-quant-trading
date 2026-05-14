"""全局配置"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据库配置
DB_DIR = PROJECT_ROOT / "data" / "db"
DB_PATH = DB_DIR / "quant.db"
DB_URL = f"sqlite:///{DB_PATH}"

# AKShare 配置
AKSHARE_RETRY_COUNT = 3
AKSHARE_RETRY_DELAY = 2  # 秒

# 日志配置
LOG_DIR = PROJECT_ROOT / "logs"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_ROTATION = "10 MB"
LOG_RETENTION = "30 days"

# 调度配置
SYNC_HOUR = 16  # 收盘后同步（A股15:00收盘，留1小时缓冲）
SYNC_MINUTE = 30

# 数据采集配置
DEFAULT_START_DATE = "20200101"  # 默认数据起始日期

# LLM 配置（OpenAI 兼容接口）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://cpa.junwei.fun/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

# ── 数据源迁移配置 ──
# 数据源模式: "legacy"=旧源(东方财富) | "new"=新源(mootdx+腾讯+AKShare) | "shadow"=新源返回+备用源后台对比
DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "new")


def _get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default



# mootdx 服务器（逗号分隔，留空则自动选择）
MOOTDX_SERVERS = os.getenv("MOOTDX_SERVERS", "")

# iwencai Cookie（问财自然语言查询需要登录态）
IWENCAI_COOKIE = os.getenv("IWENCAI_COOKIE", "")

# 影子流量采样率（0.0-1.0，shadow模式下生效）
SHADOW_SAMPLE_RATE = _get_float_env("SHADOW_SAMPLE_RATE", 0.1)

# ── qlib ML 集成配置 ──
QLIB_DATA_DIR = PROJECT_ROOT / "data" / "qlib" / "cn_data"
QLIB_MODEL_DIR = PROJECT_ROOT / "data" / "qlib" / "models"
QLIB_SERVICE_URL = os.getenv("QLIB_SERVICE_URL", "http://localhost:8002")
QLIB_PRED_CACHE = PROJECT_ROOT / "data" / "qlib" / "predictions_cache.json"
