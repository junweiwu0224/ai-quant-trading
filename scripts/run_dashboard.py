"""可视化面板启动脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import uvicorn
from loguru import logger

from config.logging import setup_logging


@click.command()
@click.option("--host", "-h", default="0.0.0.0", help="监听地址")
@click.option("--port", "-p", default=8000, help="监听端口")
@click.option("--reload", is_flag=True, help="开发模式（自动重载）")
def main(host: str, port: int, reload: bool):
    """启动可视化面板"""
    setup_logging()
    logger.info(f"面板启动: http://{host}:{port}")
    uvicorn.run(
        "dashboard.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
