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

# LLM 配置（mimo-v2.5，OpenAI 兼容接口）
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5")
