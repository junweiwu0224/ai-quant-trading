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
| quote_service | 实时行情服务（混合架构） | Xueqiu + push2delay |

**数据流：**
```
AKShare API → collector → 清洗/标准化 → storage(DB) → 策略/回测/AI
                              ↑
                    scheduler（每日16:30自动同步自选股）
                    watchlist API（添加自选股时自动采集）
```

**行情服务架构（quote_service.py）：**

采用 Xueqiu + push2delay + 腾讯混合行情架构：
- **Xueqiu**：快速行情（价格/涨跌幅/成交量），无行业/板块/概念
- **push2delay.eastmoney.com**：延迟行情 CDN，包含行业/板块/概念/市值/PE/PB
- **腾讯 fqkline API**：K 线历史数据回退（push2his 在 Docker 内不可用）
- **push2his.eastmoney.com**：K 线历史数据首选（Docker 外可用）
- **混合策略**：Xueqiu 优先，push2delay 补充行业/板块/概念，腾讯回退 K 线

```
_fetch_single_quote(code)
  ├── Xueqiu → 价格/涨跌幅/成交量
  ├── push2delay → 行业/板块/概念/市值/PE/PB
  └── _fetch_financial_data(code) → 财务指标
      ├── K 线数据（52 周高低/均量）
      │   ├── push2his 首选
      │   └── 腾讯 fqkline 回退
      ├── datacenter → EPS/BPS/ROE/毛利率/净利率/负债率
      ├── datacenter → 总股本/流通股本
      └── datacenter → PE_TTM/PS_TTM/股息率

_fetch_batch_quotes(codes)
  ├── Xueqiu 批量 → 基础行情
  └── push2delay 批量 → 补充行业/板块/概念
```

**行情详情 API（stock_detail.py）：**

K 线和分时数据采用双源回退策略：
- `/api/stock/kline/{code}` — push2his 首选，腾讯 fqkline 回退（日/周/月）
- `/api/stock/timeline/{code}` — push2delay（Docker 内可用）
- `/api/stock/detail/{code}` — 聚合接口，始终调用 `_fetch_financial_data` 补充财务指标
- `/api/stock/market/benchmark` — 沪深300 基准，push2his + 腾讯回退

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
- 主色 `#8b8680`，CSS 变量驱动，支持亮色/深色双主题
- 侧边栏 240px / 折叠 68px，响应式断点 768px/1024px/480px
- 玻璃态模态框、骨架屏加载

**总览页布局（从上到下）：**
```
┌──────────────────────────────────────────────┐
│ 核心指标卡片（总资产/当日盈亏/累计收益/最大回撤/夏普/持仓数）│
├──────────────────────────────────────────────┤
│ 市场情绪（涨跌分布/涨停/跌停）                   │
├──────────────────────────────────────────────┤
│ 市场大盘（指数/行业板块TOP10/概念板块TOP10）       │
├──────────────────────────────────────────────┤
│ 自选股管理（搜索选择+tags+表格）                  │
├──────────────────────────────────────────────┤
│ 资产走势（折线图/柱状图/基准对比）                │
├──────────────────────────────────────────────┤
│ 持仓明细                                       │
├──────────────────────────────────────────────┤
│ 最近交易                                       │
├──────────────────────────────────────────────┤
│ 系统状态（模拟盘/AI模型/行情/数据库/最新日期）     │
└──────────────────────────────────────────────┘
```

**性能优化（P0-P3）：**
| 优化 | 策略 | 效果 |
|------|------|------|
| P0 增删局部更新 | 增删自选股不调 loadOverview，局部 DOM 更新 | 增删 <200ms |
| P1 分阶段渲染 | loadOverview 拆为阶段1(核心) + 阶段2(图表市场) | 首屏 <500ms |
| P2 股票列表缓存 | 全量 6000 只缓存 5 分钟 | 下拉框 <100ms |
| P3 请求去重 | 同一股票 300ms 内不重复操作 | 防止堆积 |

**自选股管理功能：**
- 已选股票以 tags 常驻搜索框下方，点击 × 可删除
- 下拉框显示全量 5000+ 只股票，已选股票不出现在下拉框
- 删除后立即可搜索重新添加（MultiSearchBox._selected 同步清除）
- 添加后 2.5s 延迟刷新表格（等待行业/板块/概念 enrichment）
- 深色模式：localStorage 持久化偏好，支持系统 prefers-color-scheme

**Tab 页面：**
| Tab | 功能 |
|-----|------|
| 总览 | 核心指标、市场情绪、市场大盘、自选股管理、资产走势、持仓明细、最近交易、系统状态 |
| 行情详情 | 自选股搜索、K线图（北京时间）、分时图、五档盘口、阶段涨幅、专业指标、财务指标、资金流向、技术指标（MACD/KDJ/RSI/BOLL/WR/OBV）、板块/概念、行业对比 |
| 回测 | 策略选择、股票搜索（自选股下拉）、运行回测、收益曲线/月度热力图/回撤曲线/交易明细 |
| 持仓 | 持仓监控、盈亏图表、行业分布、券商账户配置 |
| 风控 | 仓位分布、风控规则状态 |
| AI Alpha | 因子重要性、训练曲线、预测对比、交易信号 |
| 模拟盘 | 启动/停止/重置、配置（策略/股票多选/资金/风控）、状态轮询 |
| 策略管理 | 策略卡片列表、新增/编辑参数/删除、内置策略只读+参数覆盖 |

**前端组件：**
| 文件 | 职责 |
|------|------|
| `app.js` | 主入口（Tab 路由、主题切换、侧边栏、总览/回测/持仓/风控/AI Alpha） |
| `overview.js` | 总览模块（分阶段渲染、图表切换、市场指数/板块） |
| `watchlist.js` | 自选股管理（局部更新、股票缓存、tags、排序） |
| `charts.js` | ChartFactory 图表工厂（line/bar/doughnut/pie/horizontalBar/showEmpty） |
| `search.js` | SearchBox 单选搜索下拉 + MultiSearchBox 多选搜索下拉 |
| `stock-detail.js` | 行情详情（自选股搜索/K线/分时/五档盘口/阶段涨幅/专业指标/财务指标/资金流向/技术指标/板块概念/行业对比） |
| `paper.js` | 模拟盘控制（启动/停止/重置/状态轮询） |
| `paper-trading.js` | 模拟盘交易面板（买卖/持仓/交易记录） |
| `portfolio.js` | 持仓模块（持仓监控/盈亏图表/行业分布） |
| `portfolio-table.js` | 持仓表格增强（排序/分页） |
| `risk.js` | 风控模块（仓位分布/风控规则） |
| `alpha.js` | AI Alpha 模块（因子/训练/预测/信号） |
| `utils.js` | 工具函数（enhanceTable/skeletonRows） |
| `realtime-quotes.js` | WebSocket 实时行情（连接/订阅/推送） |

**API 路由：**
| 路由 | 说明 |
|------|------|
| `/api/backtest/*` | 回测运行、策略列表、股票搜索、月度收益、回撤曲线、多策略对比 |
| `/api/portfolio/*` | 持仓快照、交易记录、风控状态、权益历史、行业分布、基准对比 |
| `/api/stock/*` | 股票搜索、K线、分时、资金流向、技术指标、市场指数、热门板块、市场统计 |
| `/api/system/*` | 系统状态、DB 统计 |
| `/api/alpha/*` | AI Alpha 分析（因子重要性、训练曲线、预测、信号） |
| `/api/watchlist/*` | 自选股 CRUD + F10 行业/板块/概念 enrichment |
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

*文档版本: v3.1 | 日期: 2026-05-08*
