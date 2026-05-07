"""日志配置"""
import sys
from loguru import logger
from config.settings import LOG_DIR, LOG_LEVEL, LOG_ROTATION, LOG_RETENTION


def setup_logging():
    """初始化 loguru 日志"""
    logger.remove()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )
    logger.add(
        LOG_DIR / "quant.log",
        level="DEBUG",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
