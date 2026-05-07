# 量化交易系统修复 + 前端单页改造计划

## 概述

修复所有已识别问题，将 4 页分散的 dashboard 改造为单页集成应用，优化 Docker 构建，同步到 git。

---

## 阶段 1：依赖与配置修复

### 1.1 清理 requirements.txt
- 移除 `vnpy==4.3.0`（从未导入，占数百 MB）
- 移除 `ta-lib>=0.4.28`（从未导入，增加 Docker 编译时间）
- 添加 `pydantic>=2.0`（被直接导入但未声明）
- 添加 `httpx`（TestClient 依赖）

### 1.2 简化 Dockerfile
- 移除 ta-lib C 库编译（build-essential、wget、tar 编译全删）
- 基础镜像 `python:3.11-slim` 保持不变
- 添加 `.dockerignore` 排除 `tests/`、`docs/`、`README.md`

### 1.3 添加 pytest 配置
- 创建 `pyproject.toml` 配置 pytest（testpaths、markers）

---

## 阶段 2：后端 Bug 修复

### 2.1 修复 `get_stock_list()` 方法不存在（CRITICAL）
- **文件**: `dashboard/routers/backtest.py:117`
- **问题**: 调用 `storage.get_stock_list()`，但 `DataStorage` 只有 `get_all_stock_codes()`
- **方案**: 在 `DataStorage` 中新增 `get_stock_list()` 方法，返回包含 code/name/industry 的 DataFrame
- 同时修复 `backtest.py` 中的搜索逻辑（需要 join StockInfo 表）

### 2.2 修复硬编码日期
- **文件**: `scripts/run_backtest.py:25`
- **问题**: `default="20260507"` 硬编码
- **方案**: 改为 `default=None`，运行时动态取 `datetime.now().strftime("%Y%m%d")`

### 2.3 修复相对路径问题
- **文件**: `engine/paper_engine.py`, `engine/live_engine.py`, `dashboard/routers/portfolio.py`
- **问题**: `"logs/paper"` 相对路径依赖工作目录
- **方案**: 在 `config/settings.py` 中定义 `LOG_DIR` 为绝对路径（基于 `PROJECT_ROOT`），所有引用改为 `str(PROJECT_ROOT / "logs" / "paper")`

### 2.4 添加 CORS 中间件
- **文件**: `dashboard/app.py`
- **方案**: 添加 `CORSMiddleware`，allow_origins=["*"]（开发阶段）

### 2.5 添加 StockDaily 唯一约束
- **文件**: `data/storage/storage.py`
- **方案**: 为 StockDaily 添加 `UniqueConstraint('code', 'date')`，优化去重逻辑

---

## 阶段 3：前端单页改造（核心）

### 3.1 设计思路
将 4 个独立页面（总览、回测、持仓、风控）合并为**单页 Tab 应用**：
- 侧边栏导航变为 Tab 切换（不刷新页面）
- 每个 Tab 对应一个功能区块
- 所有数据通过 AJAX 异步加载
- 共享一个 HTML 文件 + 一个 JS 文件

### 3.2 Tab 结构
```
┌─────────────────────────────────────────────────┐
│ AI Quant 量化系统                                 │
├────────┬────────────────────────────────────────┤
│ [总览]  │  内容区（Tab 切换，不刷新）               │
│ [回测]  │                                         │
│ [持仓]  │  当前 Tab 对应的完整功能区                │
│ [风控]  │                                         │
│ [策略]  │                                         │
└────────┴────────────────────────────────────────┘
```

### 3.3 各 Tab 内容

**Tab 1: 总览**
- 4 个统计卡片（总资产、现金、持仓数、今日交易）
- 系统模块状态网格
- 最近交易记录表格

**Tab 2: 回测**
- 策略选择器 + 股票搜索（自动补全）
- 日期范围 + 初始资金 + 风控开关
- 运行按钮
- 结果：6 个指标卡片 + 资金曲线图 + 交易明细表

**Tab 3: 持仓**
- 持仓快照卡片（总资产、现金、市值、持仓数）
- 持仓明细表（代码、数量、均价、市值、盈亏）
- 今日交易记录表

**Tab 4: 风控**
- 风控指标卡片（总资产、现金比例、持仓数）
- 持仓分布饼图（Chart.js Doughnut）
- 风控规则表（从 API 动态获取状态）
- 风控告警列表

**Tab 5: 策略管理（新增）**
- 策略列表（名称、类型、描述、状态）
- 策略参数展示
- 快速回测入口

### 3.4 技术实现
- **HTML**: 单个 `index.html`，5 个 Tab section，用 CSS display:none/block 切换
- **JS**: 单个 `app.js` 文件，Tab 路由 + API 调用 + Chart.js 渲染
- **CSS**: 扩展现有 `style.css`，添加 Tab 组件样式
- **后端**: 新增 `/api/strategies` 路由返回策略详情，新增 `/api/system/status` 返回系统状态

---

## 阶段 4：后端新增 API

### 4.1 系统状态 API
```
GET /api/system/status
返回: { modules: [...], db_stats: { stock_count, data_range }, ... }
```

### 4.2 策略管理 API
```
GET /api/strategies
返回: [{ name, label, type, description, params }]
```

### 4.3 风控规则 API（替代硬编码）
```
GET /api/risk/rules
返回: [{ name, threshold, current_value, status }]
```

---

## 阶段 5：测试与验证

### 5.1 修复现有测试
- 更新 `test_dashboard.py` 适配新 API
- 添加 `conftest.py` 共享 fixtures

### 5.2 运行测试
```bash
cd /home/ubuntu/quant-trading-system && python -m pytest tests/ -v
```

### 5.3 Docker 构建验证
```bash
docker compose build --no-cache
docker compose up -d
# 验证 http://localhost:8001 所有 Tab 功能
```

---

## 阶段 6：Git 同步

```bash
git add -A
git commit -m "fix: 修复依赖/Bug + 前端单页集成改造

- 移除未使用的 vnpy、ta-lib 依赖
- 修复 get_stock_list() 方法不存在
- 修复硬编码日期和相对路径问题
- 添加 CORS、pytest 配置
- 4 页 dashboard 合并为单页 Tab 应用
- 新增系统状态、策略管理、风控规则 API
- 优化 Dockerfile（移除 ta-lib 编译）"
git push origin main
```

---

## 执行顺序

1. 阶段 1（依赖修复）→ 阶段 2（Bug 修复）→ 阶段 4（新 API）→ 阶段 3（前端改造）→ 阶段 5（测试）→ 阶段 6（Git）
2. 阶段 1-2 可以并行处理
3. 阶段 3 依赖阶段 4 的 API
4. 阶段 5 依赖所有代码修改完成

## 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `requirements.txt` | 修改 | 清理依赖 |
| `Dockerfile` | 修改 | 移除 ta-lib 编译 |
| `.dockerignore` | 修改 | 排除测试和文档 |
| `pyproject.toml` | 新建 | pytest 配置 |
| `config/settings.py` | 修改 | 添加绝对路径常量 |
| `data/storage/storage.py` | 修改 | 添加唯一约束 + get_stock_list() |
| `dashboard/app.py` | 修改 | CORS + 新路由 + 精简页面路由 |
| `dashboard/routers/backtest.py` | 修改 | 修复 get_stock_list 调用 |
| `dashboard/routers/portfolio.py` | 修改 | 修复相对路径 |
| `dashboard/routers/system.py` | 新建 | 系统状态 API |
| `dashboard/templates/index.html` | 重写 | 单页 Tab 应用 |
| `dashboard/static/style.css` | 重写 | Tab 组件 + 增强样式 |
| `dashboard/static/app.js` | 新建 | 前端逻辑集中管理 |
| `scripts/run_backtest.py` | 修改 | 动态默认日期 |
| `tests/conftest.py` | 新建 | 共享 fixtures |
| `tests/test_dashboard.py` | 修改 | 适配新 API |

## 预期结果

- Docker 镜像缩小 ~500MB（移除 vnpy + ta-lib）
- Docker 构建速度提升 ~3x（无需编译 C 库）
- 所有 API 端点正常工作
- 单页 Tab 应用集成全部功能
- 测试全部通过
- 代码推送到 GitHub
