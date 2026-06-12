"""Managed OpenClaw service process lifecycle."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from config.settings import (
    OPENCLAW_AUTO_START,
    OPENCLAW_GATEWAY_PORT,
    OPENCLAW_GATEWAY_URL,
    OPENCLAW_INSTALL_TIMEOUT,
    OPENCLAW_API_KEY,
    OPENCLAW_LOG_DIR,
    OPENCLAW_MANAGED,
    OPENCLAW_NPM_PACKAGE,
    OPENCLAW_START_TIMEOUT,
    OPENCLAW_STOP_ON_EXIT,
    OPENCLAW_WORK_DIR,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PROJECT_ROOT,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpenClawServiceManager:
    """Owns the local full OpenClaw Gateway when managed mode is enabled."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.last_error = ""
        self.last_started_at = ""
        self.last_stopped_at = ""
        self.gateway_url = OPENCLAW_GATEWAY_URL
        self.port = self._port_from_url(OPENCLAW_GATEWAY_URL) or OPENCLAW_GATEWAY_PORT
        self.work_dir = Path(OPENCLAW_WORK_DIR)
        self.state_dir = self.work_dir / "state"
        self.config_path = self.work_dir / "openclaw.json"
        self.agent_workspace_dir = self.work_dir / "workspace"
        self.log_dir = Path(OPENCLAW_LOG_DIR)
        self.log_file = self.log_dir / "gateway.log"
        self.install_log_file = self.log_dir / "install.log"
        self.config_log_file = self.log_dir / "config.log"

    def _port_from_url(self, url: str) -> int | None:
        try:
            parsed = urlparse(url)
            return parsed.port
        except Exception:
            return None

    def _openclaw_bin(self) -> str:
        direct_entry = PROJECT_ROOT / "node_modules" / "openclaw" / "openclaw.mjs"
        node_bin = self._node_bin()
        if direct_entry.exists() and node_bin:
            return str(direct_entry)
        names = ["openclaw.cmd", "openclaw.ps1", "openclaw"] if os.name == "nt" else ["openclaw"]
        for name in names:
            candidate = PROJECT_ROOT / "node_modules" / ".bin" / name
            if candidate.exists():
                return str(candidate)
        found = shutil.which("openclaw")
        return found or ""

    def _npm_bin(self) -> str:
        candidates = [
            PROJECT_ROOT / ".tools" / "node-v24.14.0-win-x64" / ("npm.cmd" if os.name == "nt" else "bin/npm"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("npm") or ""

    def _node_bin(self) -> str:
        candidates = [
            PROJECT_ROOT / ".tools" / "node-v24.14.0-win-x64" / ("node.exe" if os.name == "nt" else "bin/node"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("node") or ""

    def installed(self) -> bool:
        return bool(self._openclaw_bin())

    def port_open(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def _process_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def status(self) -> dict[str, Any]:
        running = self.port_open()
        process_running = self._process_running()
        installed = self.installed()
        if not OPENCLAW_MANAGED:
            state = "external"
        elif not installed:
            state = "not_installed"
        elif running:
            state = "running"
        elif process_running:
            state = "starting"
        elif self.last_error:
            state = "failed"
        else:
            state = "stopped"
        return {
            "managed": OPENCLAW_MANAGED,
            "auto_start": OPENCLAW_AUTO_START,
            "stop_on_exit": OPENCLAW_STOP_ON_EXIT,
            "installed": installed,
            "state": state,
            "running": running,
            "process_running": process_running,
            "pid": self.process.pid if process_running and self.process else None,
            "gateway_url": self.gateway_url,
            "port": self.port,
            "bin": self._openclaw_bin(),
            "node": self._node_bin(),
            "npm": self._npm_bin(),
            "npm_package": str(OPENCLAW_NPM_PACKAGE),
            "work_dir": str(self.work_dir),
            "state_dir": str(self.state_dir),
            "config_path": str(self.config_path),
            "agent_workspace_dir": str(self.agent_workspace_dir),
            "log_file": str(self.log_file),
            "install_log_file": str(self.install_log_file),
            "config_log_file": str(self.config_log_file),
            "last_error": self.last_error,
            "last_started_at": self.last_started_at,
            "last_stopped_at": self.last_stopped_at,
            "recent_logs": self.recent_logs(),
        }

    def recent_logs(self, max_chars: int = 6000) -> str:
        try:
            if not self.log_file.exists():
                return ""
            data = self.log_file.read_text(encoding="utf-8", errors="replace")
            return data[-max_chars:]
        except Exception:
            return ""

    async def ensure_started(self) -> dict[str, Any]:
        if not OPENCLAW_MANAGED or not OPENCLAW_AUTO_START:
            return self.status()
        return await self.start()

    async def start(self) -> dict[str, Any]:
        if not OPENCLAW_MANAGED:
            self.last_error = "OPENCLAW_MANAGED=false，当前使用外部 OpenClaw 服务"
            return self.status()
        if self.port_open():
            self.last_error = ""
            return self.status()

        bin_path = await self._ensure_openclaw_cli()
        if not bin_path:
            return self.status()

        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.agent_workspace_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        await self._ensure_managed_config(bin_path)
        command = self._start_command(bin_path)
        env = {
            **os.environ,
            "OPENCLAW_CONFIG_PATH": str(self.config_path),
            "OPENCLAW_STATE_DIR": str(self.state_dir),
            "OPENCLAW_WORKSPACE_DIR": str(self.work_dir),
            "OPENCLAW_GATEWAY_PORT": str(self.port),
        }
        if OPENCLAW_API_KEY:
            env["OPENCLAW_GATEWAY_TOKEN"] = OPENCLAW_API_KEY
        try:
            log_handle = self.log_file.open("a", encoding="utf-8")
            log_handle.write(f"\n[{_utc_iso()}] starting: {' '.join(command)}\n")
            log_handle.flush()
            self.process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.last_started_at = _utc_iso()
            self.last_error = ""
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"OpenClaw 托管启动失败: {exc}")
            return self.status()

        deadline = asyncio.get_running_loop().time() + OPENCLAW_START_TIMEOUT
        while asyncio.get_running_loop().time() < deadline:
            if self.port_open():
                return self.status()
            if self.process.poll() is not None:
                self.last_error = f"OpenClaw 进程已退出，退出码 {self.process.returncode}"
                return self.status()
            await asyncio.sleep(0.5)

        self.last_error = f"OpenClaw Gateway 在 {OPENCLAW_START_TIMEOUT:.0f}s 内未监听 {self.port}"
        return self.status()

    def _start_command(self, bin_path: str) -> list[str]:
        auth_args = ["--auth", "token", "--token", OPENCLAW_API_KEY] if OPENCLAW_API_KEY else ["--auth", "none"]
        if bin_path.endswith("openclaw.mjs"):
            node_bin = self._node_bin()
            if node_bin:
                return [
                    node_bin,
                    bin_path,
                    "gateway",
                    "run",
                    "--port",
                    str(self.port),
                    "--allow-unconfigured",
                    *auth_args,
                ]
        if bin_path.endswith(".ps1"):
            return [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                bin_path,
                "gateway",
                "run",
                "--port",
                str(self.port),
                "--allow-unconfigured",
                *auth_args,
            ]
        if bin_path.endswith(".cmd") or os.name == "nt":
            return [
                bin_path,
                "gateway",
                "run",
                "--port",
                str(self.port),
                "--allow-unconfigured",
                *auth_args,
            ]
        return [
            bin_path,
            "gateway",
            "run",
            "--port",
            str(self.port),
            "--allow-unconfigured",
            *auth_args,
        ]

    async def _ensure_managed_config(self, bin_path: str) -> None:
        node_bin = self._node_bin()
        if not node_bin:
            self.last_error = "未找到可用 Node 运行时，无法初始化 OpenClaw 配置"
            return
        auth_mode = "token" if OPENCLAW_API_KEY else "none"
        commands = [
            ["config", "set", "gateway.mode", "local"],
            ["config", "set", "gateway.port", str(self.port), "--strict-json"],
            ["config", "set", "gateway.bind", "127.0.0.1"],
            ["config", "set", "gateway.auth.mode", auth_mode],
            ["config", "set", "gateway.http.endpoints.chatCompletions.enabled", "true", "--strict-json"],
            ["config", "set", "gateway.http.endpoints.responses.enabled", "true", "--strict-json"],
            ["config", "set", "agents.defaults.workspace", str(self.agent_workspace_dir)],
        ]
        provider_base_url = (OPENAI_BASE_URL or "").rstrip("/")
        provider_api_key = OPENAI_API_KEY or ""
        if provider_base_url and provider_api_key:
            provider_value = json.dumps(
                {
                    "baseUrl": provider_base_url,
                    "apiKey": "${OPENAI_API_KEY}",
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "gpt-5.5",
                            "name": "gpt-5.5",
                            "contextWindow": 200000,
                            "maxTokens": 8192,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            commands.extend([
                ["config", "set", "models.providers.subjunwei", provider_value, "--strict-json", "--merge"],
                ["config", "set", "agents.defaults.model.primary", "subjunwei/gpt-5.5"],
            ])
        else:
            commands.append(["config", "set", "agents.defaults.model.primary", "openai/gpt-5.5"])

        env = {
            **os.environ,
            "OPENCLAW_CONFIG_PATH": str(self.config_path),
            "OPENCLAW_STATE_DIR": str(self.state_dir),
            "OPENCLAW_WORKSPACE_DIR": str(self.work_dir),
            "OPENCLAW_GATEWAY_PORT": str(self.port),
        }
        if OPENCLAW_API_KEY:
            env["OPENCLAW_GATEWAY_TOKEN"] = OPENCLAW_API_KEY
        try:
            with self.config_log_file.open("a", encoding="utf-8") as log_handle:
                for args in commands:
                    log_handle.write(f"\n[{_utc_iso()}] config: {' '.join(args)}\n")
                    log_handle.flush()
                    proc = await asyncio.create_subprocess_exec(
                        node_bin,
                        bin_path,
                        *args,
                        cwd=str(PROJECT_ROOT),
                        env=env,
                        stdout=log_handle,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    code = await asyncio.wait_for(proc.wait(), timeout=OPENCLAW_INSTALL_TIMEOUT)
                    if code != 0:
                        self.last_error = f"OpenClaw 配置写入失败，退出码 {code}，查看 {self.config_log_file}"
                        return
        except asyncio.TimeoutError:
            self.last_error = f"OpenClaw 配置写入超过 {OPENCLAW_INSTALL_TIMEOUT:.0f}s"
        except Exception as exc:
            self.last_error = f"OpenClaw 配置写入失败: {exc}"
            logger.warning(self.last_error)

    async def _ensure_openclaw_cli(self) -> str:
        bin_path = self._openclaw_bin()
        if bin_path:
            return bin_path

        npm_path = self._npm_bin()
        if not npm_path:
            self.last_error = "未找到 npm，请安装 Node 22.19+ 或使用项目自带 .tools Node 运行环境"
            return ""

        package_spec = str(OPENCLAW_NPM_PACKAGE)
        package_path = Path(package_spec)
        if package_path.exists():
            package_spec = str(package_path)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        command = [npm_path, "install", "--no-audit", "--no-fund", "--save=false", package_spec]
        try:
            with self.install_log_file.open("a", encoding="utf-8") as log_handle:
                log_handle.write(f"\n[{_utc_iso()}] installing: {' '.join(command)}\n")
                log_handle.flush()
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(PROJECT_ROOT),
                    stdout=log_handle,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    code = await asyncio.wait_for(proc.wait(), timeout=OPENCLAW_INSTALL_TIMEOUT)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    self.last_error = f"OpenClaw npm 安装超过 {OPENCLAW_INSTALL_TIMEOUT:.0f}s"
                    return ""
                if code != 0:
                    self.last_error = f"OpenClaw npm 安装失败，退出码 {code}，查看 {self.install_log_file}"
                    return ""
        except Exception as exc:
            self.last_error = f"OpenClaw npm 安装失败: {exc}"
            logger.warning(self.last_error)
            return ""

        bin_path = self._openclaw_bin()
        if not bin_path:
            self.last_error = "OpenClaw 已安装但未找到 CLI 入口"
            return ""
        self.last_error = ""
        return bin_path

    async def stop(self) -> dict[str, Any]:
        if self._process_running():
            try:
                self.process.terminate()
                await asyncio.to_thread(self.process.wait, 8)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.last_stopped_at = _utc_iso()
        return self.status()

    async def restart(self) -> dict[str, Any]:
        await self.stop()
        self.last_error = ""
        return await self.start()

    async def shutdown(self) -> None:
        if OPENCLAW_STOP_ON_EXIT:
            await self.stop()


openclaw_service_manager = OpenClawServiceManager()
