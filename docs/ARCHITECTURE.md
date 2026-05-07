# A股量化交易系统 — 架构设计文档

## 1. 系统定位

基于 vnpy 引擎深度定制的个人量化交易系统，覆盖 **数据采集 → 因子研究 → 策略回测 → 模拟交易 → 实盘交易 → AI 自学习优化** 全流程。

**核心原则：**
- vnpy 做引擎底座，不重复造轮子
- 策略、AI、可视化、风控全部自研
- 模块化设计，可独立开发和替换
- 本地开发 → 云服务器部署

---

## 2. 系统架构

```
quant-trading-system/
├── data/                    # 数据层
│   ├── collector/           # 数据采集（AKShare）
│   ├── storage/             # 数据存储与管理
│   └── scheduler/           # 定时任务调度
├── strategy/                # 策略层
│   ├── templates/           # 策略模板
│   ├── builtin/             # 内置策略库
│   └── custom/              # 用户自定义策略
├── alpha/                   # AI Alpha 层
│   ├── factors/             # 因子库
│   ├── models/              # 模型训练
│   ├── optimizer/           # 超参优化
│   └── evaluator/           # 策略评估
├── risk/                    # 风控层
│   ├── position/            # 仓位管理
│   ├── stoploss/            # 止损规则
│   └── monitor/             # 风险监控
├── dashboard/               # 可视化层
│   ├── backend/             # FastAPI 后端
│   ├── frontend/            # 前端页面
│   └── websocket/           # 实时推送
├── engine/                  # vnpy 引擎集成层
│   ├── backtest/            # 回测引擎封装
│   ├── paper/               # 模拟盘封装
│   └── live/                # 实盘封装
├── config/                  # 配置文件
├── scripts/                 # 运维脚本
├── tests/                   # 测试
└── docs/                    # 文档
```

---

## 3. 模块详细设计

### 3.1 数据层 (data/)

**职责：** 采集 A股行情数据，清洗存储，供回测和实盘使用。

| 组件 | 功能 | 技术 |
|------|------|------|
| collector | 拉取日K/分钟K/Tick数据 | AKShare |
| storage | 数据清洗、入库、查询 | SQLite（开发）→ MySQL（生产） |
| scheduler | 每日收盘后自动同步 | APScheduler |

**数据流：**
```
AKShare API → collector → 清洗/标准化 → storage(DB) → 策略/回测/AI
```

**数据表设计：**
- `stock_daily` — 日K线（code, date, open, high, low, close, volume, amount）
- `stock_minute` — 分钟K线
- `stock_info` — 股票基本信息（代码、名称、行业、上市日期）
- `factor_values` — 因子值存储
- `trade_log` — 交易记录

### 3.2 策略层 (strategy/)

**职责：** 策略开发框架，提供模板和内置策略。

**策略模板：**
```python
class BaseStrategy:
    """策略基类，所有策略继承此类"""
    def on_init(self): ...       # 初始化
    def on_bar(self, bar): ...   # K线推送
    def on_order(self, order): ... # 委托回报
    def on_trade(self, trade): ... # 成交回报
```

**内置策略（首批）：**
| 策略 | 类型 | 说明 |
|------|------|------|
| 双均线策略 | 趋势 | 经典 MA 交叉 |
| 布林带策略 | 均值回归 | Bollinger Bands 突破 |
| 动量策略 | 趋势 | N日涨幅排名 |
| 海龟策略 | 趋势 | 唐奇安通道突破 |
| 网格策略 | 震荡 | 固定价格区间网格交易 |

### 3.3 AI Alpha 层 (alpha/)

**职责：** 因子挖掘、模型训练、策略自动优化。

**架构：**
```
因子库(factors) → 特征工程 → 模型训练(models) → 信号生成 → 回测验证
                                                        ↑
                                          超参优化(optimizer)
                                                        ↑
                                          策略评估(evaluator)
```

| 组件 | 功能 | 技术 |
|------|------|------|
| factors | 技术因子、基本面因子、自定义因子 | pandas, ta-lib |
| models | 机器学习模型训练与预测 | LightGBM, XGBoost, MLP |
| optimizer | 策略参数自动优化 | Optuna, Ray Tune |
| evaluator | 策略绩效评估（夏普、最大回撤等） | 自研 |

**AI 工作流：**
1. 从因子库选取候选因子
2. 特征工程（去极值、标准化、缺失值处理）
3. 模型训练（滚动窗口训练）
4. 生成交易信号
5. 回测验证 → 评估 → 参数调优 → 循环

### 3.4 风控层 (risk/)

**职责：** 资金管理、仓位控制、止损止盈。

| 规则 | 说明 |
|------|------|
| 单票仓位上限 | 不超过总资金 20% |
| 行业集中度 | 同行业不超过 40% |
| 最大回撤止损 | 回撤超 15% 全部平仓 |
| 日亏损限额 | 单日亏损超 3% 停止交易 |
| 波动率止损 | ATR 倍数止损 |
| 追踪止损 | 浮盈回撤 N% 止盈 |

### 3.5 可视化层 (dashboard/)

**职责：** Web 界面展示回测结果、实盘状态、收益曲线。

| 页面 | 功能 |
|------|------|
| 策略管理 | 查看/启停策略 |
| 回测报告 | 收益曲线、夏普比、最大回撤、交易明细 |
| 实盘监控 | 持仓、委托、成交实时展示 |
| AI Alpha | 因子重要性、模型表现、优化进度 |
| 风控面板 | 仓位分布、风险指标、告警 |

**技术选型：** FastAPI (后端) + 轻量前端（Jinja2模板 或 简单 Vue）

### 3.6 引擎集成层 (engine/)

**职责：** 封装 vnpy 引擎，提供统一接口。

| 模式 | 说明 |
|------|------|
| backtest | 回测模式，读取历史数据，批量验证策略 |
| paper | 模拟盘，接实时行情，虚拟下单 |
| live | 实盘，接 CTP/XTP 网关真实交易 |

---

## 4. 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.10+ |
| 引擎 | vnpy 4.3 |
| 数据采集 | AKShare |
| 数据库 | SQLite（开发）/ MySQL（生产） |
| AI/ML | scikit-learn, LightGBM, Optuna |
| Web框架 | FastAPI |
| 任务调度 | APScheduler |
| 容器化 | Docker + docker-compose |
| 测试 | pytest |

---

## 5. 开发阶段

### Phase 1: 基础搭建（第1-2周）
- [ ] 环境搭建（vnpy + 依赖安装）
- [ ] 数据层：AKShare 采集 → SQLite 存储
- [ ] 数据定时同步脚本
- [ ] 验证：能拉取并查询 A股日K数据

### Phase 2: 回测引擎（第3-4周）
- [ ] vnpy 回测引擎封装
- [ ] 策略模板基类
- [ ] 2-3个内置策略实现
- [ ] 回测报告生成
- [ ] 验证：双均线策略回测跑通

### Phase 3: AI Alpha（第5-7周）
- [ ] 因子库（技术因子 + 基本面因子）
- [ ] 特征工程管道
- [ ] LightGBM 模型训练
- [ ] Optuna 超参优化
- [ ] 策略评估指标体系
- [ ] 验证：模型能生成信号并通过回测验证

### Phase 4: 风控模块（第8周）
- [x] 仓位管理规则
- [x] 止损止盈规则
- [x] 风险监控告警
- [x] 验证：风控规则在回测中生效

### Phase 5: 模拟盘（第9周）
- [x] 模拟盘引擎对接
- [x] 实时行情接入
- [x] 交易日志记录
- [x] 验证：模拟盘能正常运行

### Phase 6: 可视化面板（第10-11周）
- [x] FastAPI 后端 API
- [x] 策略管理页面
- [x] 回测报告页面
- [x] 实盘监控页面
- [x] 验证：浏览器能访问并展示数据

### Phase 7: 实盘对接（第12周+）
- [x] CTP/XTP 网关配置（抽象 BrokerGateway 接口 + SimulatedBroker 实现）
- [x] 实盘交易流程（LiveTradingEngine + 风控集成）
- [x] 生产环境部署（run_live.py 启动脚本）
- [x] 验证：模拟资金小规模实盘测试

---

## 6. 部署架构

**开发环境：** 本地 Mac/Windows
**生产环境：** 云服务器 (Linux)

```
┌─────────────────────────────────┐
│         云服务器 (Linux)          │
│  ┌───────────┐ ┌──────────────┐ │
│  │ vnpy 引擎  │ │ FastAPI 服务  │ │
│  └───────────┘ └──────────────┘ │
│  ┌───────────┐ ┌──────────────┐ │
│  │ SQLite/MySQL│ │ APScheduler │ │
│  └───────────┘ └──────────────┘ │
│  ┌───────────┐ ┌──────────────┐ │
│  │ AI 训练    │ │ Nginx        │ │
│  └───────────┘ └──────────────┘ │
└─────────────────────────────────┘
```

**Docker 部署：**
```yaml
services:
  quant-engine:    # vnpy 引擎 + 策略
  quant-api:       # FastAPI 后端
  quant-web:       # 前端 + Nginx
  quant-db:        # MySQL (可选)
```

---

## 7. 目录结构详细

```
quant-trading-system/
├── docs/
│   ├── ARCHITECTURE.md          # 本文档
│   └── API.md                   # API 文档
├── data/
│   ├── __init__.py
│   ├── collector.py             # AKShare 数据采集
│   ├── cleaner.py               # 数据清洗
│   ├── storage.py               # 数据库存储
│   └── scheduler.py             # 定时同步
├── strategy/
│   ├── __init__.py
│   ├── base.py                  # 策略基类
│   ├── dual_ma.py               # 双均线策略
│   ├── bollinger.py             # 布林带策略
│   ├── momentum.py              # 动量策略
│   ├── turtle.py                # 海龟策略
│   └── grid.py                  # 网格策略
├── alpha/
│   ├── __init__.py
│   ├── factors/
│   │   ├── __init__.py
│   │   ├── technical.py         # 技术因子
│   │   └── fundamental.py       # 基本面因子
│   ├── models/
│   │   ├── __init__.py
│   │   ├── lightgbm_model.py
│   │   └── mlp_model.py
│   ├── optimizer.py             # Optuna 超参优化
│   └── evaluator.py             # 策略评估
├── risk/
│   ├── __init__.py
│   ├── position.py              # 仓位管理
│   ├── stoploss.py              # 止损规则
│   └── monitor.py               # 风险监控
├── dashboard/
│   ├── __init__.py
│   ├── app.py                   # FastAPI 入口
│   ├── routers/
│   │   ├── strategy.py
│   │   ├── backtest.py
│   │   └── monitor.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   └── backtest.html
│   └── static/
├── engine/
│   ├── __init__.py
│   ├── backtest_engine.py       # 回测引擎封装
│   ├── paper_engine.py          # 模拟盘封装
│   └── live_engine.py           # 实盘封装
├── config/
│   ├── settings.py              # 全局配置
│   └── logging.py               # 日志配置
├── scripts/
│   ├── install.sh               # 环境安装脚本
│   ├── init_db.py               # 数据库初始化
│   ├── sync_data.py             # 数据同步入口
│   └── run_backtest.py          # 回测入口
├── tests/
│   ├── test_data.py
│   ├── test_strategy.py
│   └── test_alpha.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 8. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库 | SQLite 先行 | 2核4G 轻量，后期可迁移 MySQL |
| Web 框架 | FastAPI | 异步、自动生成 API 文档、性能好 |
| AI 框架 | LightGBM + Optuna | 成熟稳定、A股场景验证过 |
| 任务调度 | APScheduler | 轻量、Python 原生、够用 |
| 前端 | Jinja2 模板优先 | 简单够用，避免引入 Node 生态 |
| 容器化 | Docker | 部署一致性、环境隔离 |

---

## 9. 风险与约束

| 风险 | 应对 |
|------|------|
| 2核4G 资源紧张 | AI 训练放本地，服务器只跑交易和数据同步 |
| vnpy 版本兼容 | 锁定 vnpy 4.3，不随意升级 |
| AKShare 接口变动 | 做好异常处理和备用数据源 |
| 实盘资金风险 | 先模拟盘验证 1 个月+ 再上实盘 |
| 网络不稳定 | 模拟盘/实盘加断线重连机制 |

---

*文档版本: v1.0 | 日期: 2026-05-07*
