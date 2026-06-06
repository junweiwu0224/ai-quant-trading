# Testing

本文件记录 AI Quant Trading 的测试策略和验证矩阵。命令细节见 `docs/commands.md`。

## 测试入口

- Pytest：`.venv/bin/python -m pytest -q`。
- 针对性 pytest：`.venv/bin/python -m pytest tests/test_<area>.py -q`。
- Python 语法检查：`.venv/bin/python -m compileall -q .`。
- E2E：启动 Dashboard 后运行 `scripts/e2e-local.sh smoke|data-health|all`，或 `npm run e2e:docker`。
- API 数据健康：`.venv/bin/python scripts/dashboard_data_health.py`。
- 前端渲染静态扫描：`.venv/bin/python scripts/frontend_data_render_audit.py`。

## 改动类型矩阵

| 改动类型 | 最小验证 | 推荐补充 |
|---|---|---|
| 文档/context pack | 路径和链接检查、`rg` 搜索引用 | 不需要跑业务测试 |
| Python 语法/导入 | `.venv/bin/python -m compileall -q .` | 相关 pytest |
| 数据/存储/调度 | 相关 `tests/test_data.py`、`tests/test_scheduler.py` 或新增针对性测试 | `.venv/bin/python -m pytest -q` |
| Signal/Qlib/机会池 | `tests/test_signal_engine.py`、`tests/test_signal_api.py`、`tests/test_qlib_*` | 对应前端契约测试 |
| Dashboard API | 对应 router 的 pytest | `.venv/bin/python scripts/dashboard_data_health.py` |
| 前端 JS/模板/CSS | 对应 `tests/test_*frontend*.py` 或契约测试 | 浏览器 smoke、`frontend_data_render_audit.py` |
| OpenClaw/LLM | 相关 `tests/test_openclaw_*` | 手动确认外部服务和凭证范围 |
| 模拟盘/交易/实盘 | 相关 engine/paper/live 测试 | 禁止未确认的真实下单或外部写操作 |
| Docker/部署 | 配置静态检查 | 用户确认后再 `docker compose up -d` |

## E2E 注意事项

- Dashboard 必须先运行，默认 `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001`。
- `scripts/e2e-local.sh` 依赖本仓库 `.tools/` 下的本地 Node/Playwright 工具链。
- `scripts/e2e.sh` 使用官方 Playwright Docker image。
- E2E 会产生 `test-results/`，该目录已在 `.gitignore` 中忽略。

## 测试环境

`tests/conftest.py` 会设置：

```python
os.environ["APP_ENV"] = "test"
```

`dashboard.app` 在 `APP_ENV=test` 下会绕过登录 session gate，便于 TestClient 覆盖 API。

## 风险和限制

- `.venv/bin/python -m compileall -q .` 会遍历整个仓库，可能触发本地 `__pycache__/` 更新。
- 全量 pytest 可能受可选依赖、外部数据源、机器环境和当前大量未提交改动影响。
- 真实数据同步、OpenClaw、LLM、Docker、实盘/券商相关验证不要放入默认自动门禁。

## 待确认

- 当前主线是否有稳定的“提交前最小测试集”。
- 是否需要新增 `make test` 或脚本统一常用验证。
