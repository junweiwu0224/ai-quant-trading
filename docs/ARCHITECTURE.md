# A股量化交易系统 — 架构设计文档

## 1. 系统定位

基于 vnpy 引擎深度定制的个人量化交易系统，覆盖 **数据采集 → 因子研究 → 策略回测 → 模拟交易 → 实盘交易 → AI 自学习优化** 全流程。

**核心原则：**
- vnpy 做引擎底座，不重复造轮子
- 策略、AI、可视化、风控全部自研
- 模块化设计，可独立开发和替换
- Docker 容器化部署

---

## 2. 系统架构

```
quant-trading-system/
├── data/                    # 数据层
│   ├── collector/           # 数据采集（AKShare）
│   ├── storage/             # 数据存储与管理（SQLite）
│   └── scheduler/           # 定时任务调度（APScheduler）
├── strategy/                # 策略层
│   ├── manager.py           # 策略持久化管理（内置+自定义）
│   ├── dual_ma.py           # 双均线策略
│   ├── bollinger.py         # 布林带策略
│   └── momentum.py          # 动量策略
├── alpha/                   # AI Alpha 层
│   ├── factors/             # 因子库
│   ├── models/              # 模型训练（LightGBM）
│   └── optimizer/           # 超参优化（Optuna）
├── risk/                    # 风控层
│   ├── position/            # 仓位管理
│   ├── stoploss/            # 止损规则
│   └── monitor/             # 风险监控
├── dashboard/               # 可视化层（FastAPI + Jinja2 SPA）
│   ├── app.py               # FastAPI 入口（含 lifespan 调度器）
│   ├── routers/             # API 路由
│   ├── templates/           # HTML 模板
│   └── static/              # 前端资源（JS/CSS）
├── engine/                  # vnpy 引擎集成层
│   ├── backtest_engine.py   # 回测引擎
│   ├── paper_engine.py      # 模拟盘引擎
│   ├── live_engine.py       # 实盘引擎
│   └── broker.py            # BrokerGateway 抽象接口
├── config/                  # 配置
├── scripts/                 # 运维脚本
└── docs/                    # 文档
```

---

## 3. 模块详细设计

### 3.1 数据层 (data/)

**职责：** 采集 A股行情数据，清洗存储，供回测和实盘使用。

| 组件 | 功能 | 技术 |
|------|------|------|
| collector | 拉取日K数据 | AKShare |
| storage | 数据清洗、入库、查询、自选股管理 | SQLite |
| scheduler | 后台定时同步自选股数据 | APScheduler BackgroundScheduler |

**数据流：**
```
AKShare API → collector → 清洗/标准化 → storage(DB) → 策略/回测/AI
                              ↑
                    scheduler（每日16:30自动同步自选股）
                    watchlist API（添加自选股时自动采集）
```

**数据表：**
- `stock_info` — A股基本信息（代码、名称、行业），5500+ 只
- `stock_daily` — 日K线（code, date, open, high, low, close, volume, amount）
- `user_watchlist` — 用户自选股列表

### 3.2 策略层 (strategy/)

**职责：** 策略开发框架，提供模板和内置策略。

**策略管理：**
- `StrategyManager` 持久化管理（`data/strategies.json`）
- 内置策略（dual_ma / bollinger / momentum）支持参数覆盖
- 自定义策略 CRUD（新增/编辑/删除）
- 前端结构化参数编辑表单

**内置策略：**
| 策略 | 类型 | 参数 |
|------|------|------|
| 双均线策略 | 趋势 | short_window=5, long_window=20 |
| 布林带策略 | 均值回归 | window=20, num_std=2 |
| 动量策略 | 趋势 | lookback=20, entry_threshold=0.1 |

### 3.3 AI Alpha 层 (alpha/)

**职责：** 因子挖掘、模型训练、信号生成。

| 组件 | 功能 | 技术 |
|------|------|------|
| factors | 技术因子（MA/MACD/RSI/ATR等） | pandas |
| models | LightGBM 模型训练与预测 | LightGBM |
| optimizer | 超参优化 | Optuna |

**前端展示：** 因子重要性 Top20、训练曲线（AUC/Loss）、预测 vs 实际、K线交易信号。

### 3.4 风控层 (risk/)

**职责：** 资金管理、仓位控制、止损止盈。

| 规则 | 说明 |
|------|------|
| 单票仓位上限 | 不超过总资金 20% |
| 行业集中度 | 同行业不超过 40% |
| 最大回撤止损 | 回撤超 15% 全部平仓 |
| 日亏损限额 | 单日亏损超 3% 停止交易 |

### 3.5 可视化层 (dashboard/)

**职责：** Web 界面，SPA 架构，7 个功能 Tab。

**技术栈：** FastAPI + Jinja2 + Vanilla JS + Chart.js v4

**设计系统：** 对标 cli-proxy-api 暖灰色系设计
- 主色 `#8b8680`，CSS 变量驱动
- 侧边栏 240px / 折叠 68px，响应式断点 768px/1024px/480px
- 玻璃态模态框、骨架屏加载

**Tab 页面：**
| Tab | 功能 |
|-----|------|
| 总览 | 系统状态、资产走势、收益分布、自选股管理 |
| 回测 | 策略选择、股票搜索（自选股下拉）、运行回测、收益曲线/月度热力图/回撤曲线/交易明细 |
| 持仓 | 持仓监控、盈亏图表、行业分布、券商账户配置 |
| 风控 | 仓位分布、风控规则状态 |
| AI Alpha | 因子重要性、训练曲线、预测对比、交易信号 |
| 模拟盘 | 启动/停止/重置、配置（策略/股票多选/资金/风控）、状态轮询 |
| 策略管理 | 策略卡片列表、新增/编辑参数/删除、内置策略只读+参数覆盖 |

**前端组件：**
| 文件 | 职责 |
|------|------|
| `charts.js` | ChartFactory 图表工厂（line/bar/doughnut/pie/horizontalBar/showEmpty） |
| `search.js` | SearchBox 单选搜索下拉 + MultiSearchBox 多选搜索下拉（搜索内置在下拉中） |
| `watchlist.js` | 自选股管理（添加/删除/同步数据） |
| `paper.js` | 模拟盘控制（启动/停止/重置/状态轮询） |
| `strategy.js` | 策略 CRUD + 结构化参数表单 |
| `app.js` | 主入口（Tab 路由、总览/回测/持仓/风控/AI Alpha、券商配置） |

**API 路由：**
| 路由 | 说明 |
|------|------|
| `/api/backtest/*` | 回测运行、策略列表、股票搜索、月度收益、回撤曲线、多策略对比 |
| `/api/portfolio/*` | 持仓快照、交易记录、风控状态、权益历史、行业分布 |
| `/api/system/*` | 系统状态、DB 统计 |
| `/api/alpha/*` | AI Alpha 分析（因子重要性、训练曲线、预测、信号） |
| `/api/watchlist/*` | 自选股 CRUD + 数据同步 |
| `/api/paper/*` | 模拟盘控制（start/stop/reset/status） |
| `/api/strategy/*` | 策略 CRUD（内置策略参数覆盖） |
| `/api/broker/*` | 券商账户配置 |

### 3.6 引擎集成层 (engine/)

**职责：** 封装 vnpy 引擎，提供统一接口。

| 模式 | 说明 | 状态 |
|------|------|------|
| backtest | 回测模式，读取历史数据，批量验证策略 | 已实现 |
| paper | 模拟盘，接实时行情，虚拟下单 | 已实现 |
| live | 实盘，接 CTP/XTP 网关真实交易 | 接口已定义，Gateway 未实现 |

**BrokerGateway 抽象接口：**
```python
class BrokerGateway(ABC):
    connect() / disconnect()
    get_account() / get_positions()
    place_order() / cancel_order() / get_order_status()
```
当前仅有 `SimulatedBroker` 实现（内存撮合）。

---

## 4. 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11 |
| 引擎 | vnpy 4.3 |
| 数据采集 | AKShare |
| 数据库 | SQLite |
| AI/ML | LightGBM, Optuna |
| Web 框架 | FastAPI + Jinja2 |
| 前端 | Vanilla JS + Chart.js v4 |
| 任务调度 | APScheduler |
| 容器化 | Docker + docker-compose |
| 反向代理 | Nginx + Cloudflare CDN |

---

## 5. 开发进度

### Phase 1: 基础搭建 — 已完成
- [x] AKShare 数据采集 → SQLite 存储
- [x] 数据定时同步（DataScheduler 后台线程，每日 16:30 同步自选股）
- [x] 自选股管理（UserWatchlist 表 + API）
- [x] 股票列表 5500+ 只

### Phase 2: 回测引擎 — 已完成
- [x] BacktestEngine 回测引擎
- [x] 3 个内置策略（双均线/布林带/动量）
- [x] 策略参数持久化 + 内置策略参数覆盖
- [x] 回测报告（收益曲线/月度热力图/回撤曲线/交易明细/风控告警）
- [x] 多策略收益对比

### Phase 3: AI Alpha — 已完成
- [x] 技术因子库（MA/MACD/RSI/ATR 等）
- [x] LightGBM 模型训练
- [x] Optuna 超参优化
- [x] 前端展示（因子重要性/训练曲线/预测对比/交易信号）

### Phase 4: 风控模块 — 已完成
- [x] 仓位管理规则
- [x] 止损止盈规则
- [x] 风险监控告警
- [x] 风控面板可视化

### Phase 5: 模拟盘 — 已完成
- [x] PaperEngine 模拟盘引擎
- [x] 实时行情接入
- [x] Dashboard 控制面板（启动/停止/重置/状态轮询）
- [x] 多选股票配置

### Phase 6: 可视化面板 — 已完成
- [x] FastAPI 后端 API（7 组路由）
- [x] SPA 前端（7 个 Tab）
- [x] 响应式布局（桌面/平板/手机）
- [x] 暖灰色设计系统
- [x] 搜索下拉组件（单选/多选，搜索内置在下拉中）
- [x] 自选股管理 + 数据同步
- [x] 策略 CRUD + 结构化参数编辑
- [x] 券商账户配置入口

### Phase 7: 实盘对接 — 接口就绪，Gateway 未实现
- [x] BrokerGateway 抽象接口定义
- [x] SimulatedBroker 实现（内存撮合）
- [x] LiveTradingEngine 框架
- [ ] CTP Gateway 实现（期货）
- [ ] XTP Gateway 实现（股票）
- [ ] 券商配置 UI（已预留入口）

---

## 6. 未来规划

### 短期
- [ ] 实现 CTP/XTP BrokerGateway，对接真实券商
- [ ] 自选股同步优化（增量更新、断点续传）
- [ ] 回测参数优化（网格搜索 / 遗传算法）

### 中期
- [ ] 分钟K线 / Tick 数据采集
- [ ] 多因子组合策略
- [ ] 策略绩效归因分析
- [ ] 实盘交易日志 + 对账

### 长期
- [ ] 多账户管理
- [ ] 策略组合管理（FOF）
- [ ] 实时风控推送（WebSocket）
- [ ] 移动端适配

---

## 7. 部署架构

```
┌─────────────────────────────────────────┐
│           云服务器 (Docker)               │
│                                         │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │  Dashboard    │  │  Paper Engine   │  │
│  │  (FastAPI)    │  │  (模拟盘)       │  │
│  │  :8001        │  │                 │  │
│  └──────────────┘  └─────────────────┘  │
│                                         │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │  SQLite DB   │  │  Data Scheduler │  │
│  │  (data/db/)  │  │  (后台线程)      │  │
│  └──────────────┘  └─────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │  Nginx → Cloudflare CDN          │   │
│  │  biga.junwei.fun → :8001         │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

*文档版本: v2.0 | 日期: 2026-05-07*
