"""可视化面板启动脚本

同时启动 qlib 推理微服务（后台子进程），统一在一个容器内管理。
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import uvicorn
from loguru import logger

from config.logging import setup_logging


def _start_qlib_service(qlib_port: int) -> subprocess.Popen | None:
    """启动 qlib 推理微服务作为后台子进程"""
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "qlib_service.log", "a")

    cmd = [
        sys.executable, "-m", "data.qlib.service",
        "--port", str(qlib_port),
        "--auto-train",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        logger.info(f"qlib 推理服务已启动 (pid={proc.pid}, port={qlib_port}, log={log_dir / 'qlib_service.log'})")
        return proc
    except Exception as e:
        logger.warning(f"qlib 服务启动失败（非致命）: {e}")
        return None


@click.command()
@click.option("--host", "-h", default="0.0.0.0", help="监听地址")
@click.option("--port", "-p", default=8000, help="监听端口")
@click.option("--qlib-port", default=8002, help="qlib 服务端口")
@click.option("--no-qlib", is_flag=True, help="不启动 qlib 服务")
@click.option("--reload", is_flag=True, help="开发模式（自动重载）")
def main(host: str, port: int, qlib_port: int, no_qlib: bool, reload: bool):
    """启动可视化面板"""
    setup_logging()

    qlib_proc = None
    if not no_qlib:
        qlib_proc = _start_qlib_service(qlib_port)

    logger.info(f"面板启动: http://{host}:{port}")
    try:
        uvicorn.run(
            "dashboard.app:app",
            host=host,
            port=port,
            reload=reload,
        )
    finally:
        if qlib_proc and qlib_proc.poll() is None:
            qlib_proc.terminate()
            qlib_proc.wait(timeout=5)
            logger.info("qlib 推理服务已停止")


if __name__ == "__main__":
    main()
