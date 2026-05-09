# A股量化交易系统 — 架构设计文档

## 1. 系统定位

基于 vnpy 引擎深度定制的个人量化交易系统，覆盖 **数据采集 → 因子研究 → 策略回测 → 模拟交易 → AI 自学习优化** 全流程。

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
│   ├── collector/           # 数据采集（AKShare）+ HTTP 客户端
│   ├── storage/             # 数据存储与管理（SQLite + SQLAlchemy）
│   └── scheduler/           # 定时任务调度（APScheduler）
├── strategy/                # 策略层
│   ├── manager.py           # 策略持久化管理（内置+自定义）
│   ├── version.py           # 策略版本管理（保存/回滚/Diff）
│   ├── dual_ma.py           # 双均线策略
│   ├── bollinger.py         # 布林带策略
│   └── momentum.py          # 动量策略
├── alpha/                   # AI Alpha 层
│   ├── factors/             # 因子库（技术/基本面/资金流/情绪/宏观）
│   ├── models/              # 模型（LightGBM/XGBoost/Ensemble）
│   ├── feature_pipeline.py  # 特征工程管道
│   ├── cross_sectional.py   # 跨截面选股模型
│   ├── backtest.py          # 组合回测引擎（含成本/约束/分配）
│   ├── screener.py          # 条件选股引擎
│   ├── llm_client.py        # LLM 客户端（mimo-v2.5）
│   ├── nl_strategy.py       # 自然语言策略生成 + AI 解读
│   └── factor_scheduler.py  # 因子动态更新调度器
├── risk/                    # 风控层
│   ├── position/            # 仓位管理
│   ├── stoploss/            # 止损规则（固定/跟踪/ATR/回撤）
│   └── monitor/             # 风险监控
├── dashboard/               # 可视化层（FastAPI + Jinja2 SPA）
│   ├── app.py               # FastAPI 入口（含 lifespan 调度器）
│   ├── routers/             # API 路由（17 组，120+ 端点）
│   ├── templates/           # HTML 模板
│   └── static/              # 前端资源（35 个 JS/CSS 模块）
├── engine/                  # 引擎集成层
│   ├── backtest_engine.py   # 回测引擎
│   ├── paper_engine.py      # 模拟盘引擎
│   ├── live_engine.py       # 实盘引擎
│   ├── alert_engine.py      # 预警引擎
│   ├── broker.py            # BrokerGateway 抽象接口
│   ├── report_generator.py  # PDF 报告生成
│   └── performance_analyzer.py  # 绩效分析（Brinson归因/Monte Carlo）
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
| http_client | 共享 httpx 连接池、fetch_json/code_to_secid/fetch_kline | httpx |
| storage | 数据清洗、入库、查询、自选股管理、预警规则、画线保存 | SQLAlchemy + SQLite |
| scheduler | 后台定时同步自选股数据 | APScheduler |
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

**数据表：**
| 表 | 说明 |
|----|------|
| `stock_info` | A股基本信息（代码、名称、行业），5500+ 只 |
| `stock_daily` | 日K线（code, date, open, high, low, close, volume, amount） |
| `user_watchlist` | 用户自选股列表 |
| `strategy_version` | 策略版本历史 |
| `backtest_record` | 回测记录持久化 |
| `alert_rules` | 预警规则 |
| `chart_drawings` | K 线画线标注 |

### 3.2 策略层 (strategy/)

**职责：** 策略开发框架，提供模板和内置策略。

**策略管理：**
- `StrategyManager` 持久化管理（`data/strategies.json`）
- 内置策略（dual_ma / bollinger / momentum）支持参数覆盖
- 自定义策略 CRUD + AST 安全验证（白名单 import、禁止危险内置函数）
- 策略版本管理（保存/回滚/Diff）
- 回测记录持久化（保存/加载/对比）

**内置策略：**
| 策略 | 类型 | 参数 |
|------|------|------|
| 双均线策略 | 趋势 | short_window=5, long_window=20 |
| 布林带策略 | 均值回归 | window=20, num_std=2 |
| 动量策略 | 趋势 | lookback=20, entry_threshold=0.1 |

### 3.3 AI Alpha 层 (alpha/)

**职责：** 因子挖掘、模型训练、信号生成、跨截面选股。

#### 因子库 (alpha/factors/)

| 模块 | 因子 | 来源 |
|------|------|------|
| technical.py | MA/EMA/RSI/MACD/Bollinger/ATR/KDJ/多期收益/波动率 | K 线数据 |
| fundamental.py | 代理因子（换手率/动量/VPT/MFI/MA偏离/成交量Z-score）+ 真实财务（PE/ROE/EPS/BPS/毛利率/净利率/营收增长/净利润增长/负债率/股息率） | 价量数据 + 东方财富 datacenter |
| flow.py | 北向持股比例/变化/连续净买入/累计净买入 + 龙虎榜上榜次数/机构净买入/热度 | 东方财富北向/龙虎榜 API |
| sentiment.py | 情绪分/3日均/5日均/变化率 | 东方财富公告 API + SnowNLP |
| macro.py | SHIBOR 1W/1M、国债收益率 10Y/1Y、M2 增速、社融 | 东方财富宏观数据 API |

#### 模型 (alpha/models/)

| 模型 | 说明 |
|------|------|
| LightGBM | 二分类器，AUC 指标，200 estimators，early stopping |
| XGBoost | 二分类器，AUC 指标，200 estimators，early stopping |
| Ensemble | 加权平均或多数投票集成 LGB+XGB |

#### 核心模块

| 模块 | 功能 |
|------|------|
| feature_pipeline.py | 特征管道：技术+基本面+可选API因子 → 去极值 → 标准化 → 标签 |
| cross_sectional.py | 跨截面选股：全市场因子矩阵 → 截面标签 → 集成训练 → TOP N 预测 |
| backtest.py | 组合回测：等权/风险平价/因子加权分配，含成本模型和行业约束 |
| screener.py | 条件选股：字段+运算符+值过滤，6 预设策略，批量获取行情 |
| factor_scheduler.py | 因子调度：交易时段高频（北向15min/板块30min/情绪1h/宏观日更），盘后降频 |
| llm_client.py | mimo-v2.5 LLM 客户端（OpenAI 兼容接口，异步调用） |
| nl_strategy.py | 自然语言→选股条件 JSON + AI 预测结果解读 + 量化对话 |

#### 可解释性

- **SHAP 全局重要性**：Top 20 因子柱状图
- **SHAP 依赖图**：因子值 vs SHAP 值散点
- **SHAP 蜂群图**：全部因子贡献分布
- **因子 IC/IR**：因子与未来收益的信息系数/信息比率
- **因子衰减**：IC vs 持有期
- **因子相关性**：热力图矩阵
- **自动因子挖掘**：diff/ratio/product 组合，按 IC 排序

### 3.4 风控层 (risk/)

**职责：** 资金管理、仓位控制、止损止盈。

| 规则 | 说明 |
|------|------|
| 单票仓位上限 | 不超过总资金 20% |
| 行业集中度 | 同行业不超过 40% |
| 最大持仓数 | 不超过 10 只 |
| 最大回撤止损 | 回撤超 15% 全部平仓 |
| 日亏损限额 | 单日亏损超 3% 停止交易 |
| 固定止损 | 5% |
| 跟踪止损 | 8% |
| ATR 止损 | 2x ATR |

### 3.5 预警引擎 (engine/alert_engine.py)

**职责：** 实时监控行情，触发条件预警。

| 条件 | 说明 |
|------|------|
| price_above | 价格突破上限 |
| price_below | 价格跌破下限 |
| change_above | 涨幅超阈值 |
| change_below | 跌幅超阈值 |
| volume_ratio_above | 量比超阈值 |
| turnover_above | 换手率超阈值 |
| amplitude_above | 振幅超阈值 |

- 防重复触发：cooldown 机制（默认 5 分钟）
- WebSocket 广播：触发后推送到所有客户端
- 持久化：SQLite alert_rules 表

### 3.6 可视化层 (dashboard/)

**职责：** Web 界面，SPA 架构，8 个功能 Tab + 多个子页面。

**技术栈：** FastAPI + Jinja2 + Vanilla JS + Chart.js v4 + KlineCharts v9

**设计系统：** 暖灰色系设计
- 主色 `#8b8680`，CSS 变量驱动，支持亮色/深色双主题
- 侧边栏 240px / 折叠 68px，响应式断点 768px/1024px/480px
- 玻璃态模态框、骨架屏加载

**Tab 页面：**

| Tab | 子页面 | 功能 |
|-----|--------|------|
| 总览 | — | 核心指标、市场情绪、指数、热力板块、市场雷达、条件选股、AI选股、预警中心、自选股、资产走势、持仓明细 |
| 行情详情 | — | K线图（画线工具/多周期）、分时图、五档盘口、筹码分布、资金流向、财务数据、行业对比、北向资金、多股对比 |
| 回测 | — | 策略选择、股票搜索、回测运行、收益曲线、月度热力图、回撤曲线、交易明细、Monte Carlo、Walk-Forward、Brinson归因、PDF报告 |
| 持仓 | — | 持仓监控、风险指标（VaR/Sharpe/Sortino/Calmar）、行业分布、相关性矩阵、止损止盈、导出 |
| 风控 | — | 仓位分布、风控规则状态、风险事件日志 |
| AI Alpha | 模型分析 | 训练曲线（AUC/Loss）、因子重要性 Top20 |
| | 因子研究 | IC/IR、量化收益、相关性矩阵、衰减分析 |
| | 交易信号 | K线+买卖信号叠加、策略绩效模拟 |
| | 模型对比 | LightGBM vs XGBoost vs Ensemble |
| | Walk-Forward | 滚动窗口验证、稳定性分析 |
| | 因子挖掘 | 自动组合因子、IC 排序 |
| 模拟盘 | — | 启动/停止/重置、订单管理（市价/限价/止损/止盈）、持仓管理、绩效指标、权益曲线、交易统计、月度热力图 |
| 策略管理 | — | 策略列表、代码编辑器、AST安全验证、版本管理 |
| AI 助手 | — | LLM 流式对话、自然语言→选股条件、AI 结果解读 |

**前端模块（35 个）：**

| 文件 | 职责 |
|------|------|
| `app.js` | 主入口（Tab 路由、主题切换、侧边栏） |
| `overview.js` | 总览模块（分阶段渲染、图表切换） |
| `watchlist.js` | 自选股管理（局部更新、tags） |
| `stock-detail.js` | 行情详情（K线/分时/五档/筹码/财务/行业对比） |
| `compare.js` | 多股对比（归一化收益率、缩放/滚动） |
| `screener.js` | 条件选股 + AI 选股 |
| `alerts.js` | 预警管理（规则 CRUD、触发历史、Toast 通知） |
| `overview-radar.js` | 市场雷达（TOP10、板块轮动、北向资金） |
| `backtest.js` | 回测（Monte Carlo、Walk-Forward、归因） |
| `portfolio.js` | 持仓管理（风险指标、相关性矩阵） |
| `risk.js` | 风控模块 |
| `alpha.js` | AI Alpha（SHAP、因子评估、模型对比） |
| `paper.js` | 模拟盘控制 |
| `paper-trading.js` | 模拟盘交易面板 |
| `strategy.js` | 策略管理（代码编辑器、版本管理） |
| `llm.js` | AI 助手（SSE 流式对话、条件预览） |
| `charts.js` | ChartFactory 图表工厂 |
| `search.js` | 搜索下拉组件（单选/多选） |
| `realtime.js` | WebSocket 实时行情 |
| `utils.js` | 工具函数 |

**API 路由（17 组）：**

| 路由 | 端点数 | 说明 |
|------|--------|------|
| `/api/backtest/*` | 17+ | 回测运行、策略列表、Monte Carlo、Walk-Forward、Brinson归因、PDF报告 |
| `/api/portfolio/*` | 18+ | 持仓快照、交易记录、风险指标、行业分布、相关性、导出 |
| `/api/stock/*` | 20+ | 股票搜索、K线、分时、五档、筹码、画线、多股对比、市场指数/板块 |
| `/api/alpha/*` | 15+ | 因子评估、SHAP、模型对比、因子挖掘、跨截面训练/预测、组合回测 |
| `/api/screener/*` | 4 | 条件选股、预设策略、字段列表 |
| `/api/alerts/*` | 6 | 预警规则 CRUD、触发历史、条件类型 |
| `/api/market/*` | 3 | 市场雷达、板块轮动、北向资金 |
| `/api/paper/*` | 25+ | 模拟盘控制、订单/持仓管理、绩效/统计、风控 |
| `/api/strategy/*` | 6 | 策略 CRUD、代码验证 |
| `/api/strategy-version/*` | 9 | 策略版本管理、回测记录 |
| `/api/watchlist/*` | 4 | 自选股 CRUD + enrichment |
| `/api/llm/*` | 3 | LLM 对话、策略生成、结果解读 |
| `/api/broker/*` | 4 | 券商配置 |
| `/api/system/*` | 3 | 系统状态 |

**WebSocket 端点：**
| 端点 | 说明 |
|------|------|
| `/ws/quotes` | 实时行情推送（订阅/退订/预警广播） |
| `/api/backtest/ws/run` | 回测实时进度 |
| `/api/backtest/ws/walk-forward` | Walk-Forward 实时进度 |
| `/api/optimization/ws/run` | 参数优化实时进度 |

### 3.7 引擎集成层 (engine/)

**职责：** 封装 vnpy 引擎，提供统一接口。

| 模式 | 说明 | 状态 |
|------|------|------|
| backtest | 回测模式，读取历史数据，批量验证策略 | 已实现 |
| paper | 模拟盘，接实时行情，虚拟下单 | 已实现 |
| live | 实盘，接 CTP/XTP 网关真实交易 | 接口已定义，Gateway 未实现 |

---

## 4. 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11 |
| 引擎 | vnpy 4.3 |
| 数据采集 | AKShare |
| 实时行情 | Xueqiu + push2delay + 腾讯 fqkline |
| 数据库 | SQLite + SQLAlchemy |
| AI/ML | LightGBM, XGBoost, Optuna, SHAP |
| NLP | SnowNLP, mimo-v2.5 (LLM) |
| Web 框架 | FastAPI + Jinja2 |
| 前端 | Vanilla JS + Chart.js v4 + KlineCharts v9 |
| 任务调度 | APScheduler |
| 容器化 | Docker + docker-compose |
| 反向代理 | Nginx + Cloudflare CDN |

---

## 5. 开发进度

### Phase 1: K线技术分析增强 — 已完成
- [x] 画线工具（趋势线/水平线/斐波那契，保存/加载/删除）
- [x] 多周期切换（1m/5m/15m/30m/60m/日/周/月）
- [x] 多股对比（归一化收益率，缩放/滚动/区间标注）

### Phase 2: 条件选股系统 — 已完成
- [x] StockScreener 核心（字段+运算符+值过滤）
- [x] 6 预设策略模板
- [x] 选股 API + 前端（条件构建器、结果表格、CSV 导出）

### Phase 3: AI 跨截面选股模型 — 已完成
- [x] CrossSectionalPipeline（全市场因子矩阵 + 截面标签 + 集成训练 + 预测）
- [x] LightGBM + XGBoost 软投票集成
- [x] 训练 API + Walk-Forward 验证
- [x] 组合回测引擎（等权/风险平价/因子加权，含成本模型和行业约束）
- [x] AI 选股前端（推荐列表、SHAP 贡献、策略收益曲线）

### Phase 4: 预警系统 — 已完成
- [x] AlertEngine（7 种条件、防重复触发）
- [x] WebSocket 推送（实时预警广播）
- [x] 预警管理 API + 前端（CRUD、触发历史）

### Phase 5: 筹码分布 + 市场雷达 — 已完成
- [x] 筹码分布图（获利比例/平均成本/集中度）
- [x] 市场雷达（涨幅/跌幅/振幅/换手率/量比 TOP10）
- [x] 板块轮动排名 + 北向资金净流入

### Phase 6: 因子增强 + 数据源扩展 — 已完成
- [x] 真实财务因子（PE/ROE/EPS/毛利率/净利率/营收增长/净利润增长/负债率/股息率）
- [x] 北向资金因子（持股比例/变化/连续净买入/累计净买入）
- [x] 龙虎榜因子（上榜次数/机构净买入/热度评分）
- [x] 新闻情绪因子（SnowNLP + 关键词降级，3/5日均值，变化率）
- [x] 宏观因子（SHIBOR/国债/M2/社融）
- [x] 因子动态更新调度器（交易时段高频，盘后降频）
- [x] 特征管道集成（enable_api_factors 开关）

### Phase 7: LLM 集成 — 已完成
- [x] mimo-v2.5 LLM 客户端（OpenAI 兼容，异步调用）
- [x] 自然语言→选股条件 JSON
- [x] AI 预测结果解读（理由/因子/风险/建议）
- [x] 流式对话 SSE
- [x] AI 助手前端（对话界面、条件预览卡片）

### 基础设施 — 已完成
- [x] AKShare 数据采集 → SQLite 存储
- [x] 数据定时同步（每日 16:30）
- [x] 自选股管理 + F10 enrichment
- [x] 模拟盘引擎（市价/限价/止损/止盈单）
- [x] 风控模块（仓位/止损/监控）
- [x] 策略版本管理 + 回测记录持久化
- [x] PDF 报告生成
- [x] 响应式布局 + 深色模式

---

## 6. 待开发（竞品对标）

对标通达信、QMT、PTrade、AI涨乐、同花顺 iQuant 等竞品分析后的改进计划。

### 第一优先级 — 高 ROI

| # | 功能 | 对标竞品 | 说明 | 难度 |
|---|------|---------|------|------|
| 1 | 公式系统 | 通达信 | 类通达信语法公式引擎，支持自定义指标/选股公式（`CROSS(MA5,MA20)`），降低策略编写门槛 | ★★★ |
| 2 | 条件单 | QMT/PTrade | 预警触发后自动下单（止盈止损单、拐点单、回落卖出单） | ★★ |
| 3 | 篮子交易 | QMT/PTrade | AI 选股 TOP20 一键组合买入，等权/风险平价分配 | ★★ |
| 4 | 板块热力图 | 同花顺 | 行业 x 涨跌幅色块可视化，一眼看出资金流向 | ★★ |
| 5 | 多周期共振 | 通达信 | 一屏 4 窗口（日/60 分钟/周/月），自动标注共振信号 | ★★ |

### 第二优先级 — 体验提升

| # | 功能 | 对标竞品 | 说明 | 难度 |
|---|------|---------|------|------|
| 6 | 分时图增强 | 通达信 | 分时均价线、量比实时曲线、多日分时叠加 | ★★ |
| 7 | 龙虎榜深度分析 | 东方财富 Choice | 机构 vs 游资趋势图、游资席位画像、上榜后收益统计 | ★★ |
| 8 | 研报整合 | 东方财富 Choice | 接入研报数据，LLM 自动解读研报观点 | ★★ |
| 9 | 移动端 PWA | 涨乐财富通 | PWA + 离线缓存 + 推送通知 | ★★★ |
| 10 | 策略导入导出 | 通达信公式社区 | JSON 策略分享、社区评分排行 | ★★ |

### 第三优先级 — 长线投入

| # | 功能 | 对标竞品 | 说明 | 难度 |
|---|------|---------|------|------|
| 11 | Tick 级回测 | QMT | 分钟级/Tick 级回测引擎，支持日内策略 | ★★★★ |
| 12 | L2 十档行情 | QMT/PTrade | 十档买卖盘、逐笔成交、委托队列 | ★★★ |
| 13 | 可转债/期权 | QMT | 扩展交易品种，可转债套利策略 | ★★★ |
| 14 | 实盘交易 | QMT/PTrade | CTP/XTP BrokerGateway 对接真实券商 | ★★★★★ |

---

## 7. 竞品对比总结

| 维度 | 通达信 | QMT | PTrade | AI涨乐 | **本系统** |
|------|--------|-----|--------|--------|-----------|
| 公式系统 | ✅ 成熟 | ❌ | ❌ | ❌ | ❌ 待开发 |
| 条件单 | ✅ | ✅ | ✅ | ✅ | ❌ 待开发 |
| 篮子交易 | ❌ | ✅ | ✅ | ❌ | ❌ 待开发 |
| AI 选股 | ❌ | ❌ | ❌ | ✅ 黑盒 | ✅ 白盒+SHAP |
| 因子研究 | ❌ | 基础 | 基础 | ❌ | ✅ IC/IR/衰减/挖掘 |
| 回测深度 | 基础 | ✅ tick级 | ✅ | ❌ | ✅ Monte Carlo/WF/Brinson |
| 可解释性 | ❌ | ❌ | ❌ | ❌ | ✅ SHAP 全套 |
| LLM 集成 | ❌ | ❌ | ❌ | 基础 | ✅ NL策略+解读+对话 |
| 策略版本 | ❌ | ❌ | ❌ | ❌ | ✅ 保存/回滚/Diff |
| 模拟盘 | ❌ | ✅ | ✅ | ❌ | ✅ 完整订单管理 |
| 实盘交易 | ✅ | ✅ | ✅ | ✅ | ❌ 待对接 |

**核心优势：** AI 可解释性（SHAP）、因子研究深度、LLM 集成、回测分析深度、策略版本管理
**核心短板：** 公式系统、条件单、篮子交易、实盘对接

---

## 8. 部署架构

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
│  ┌──────────────┐  ┌─────────────────┐  │
│  │  Alert Engine│  │  Factor Sched.  │  │
│  │  (预警引擎)   │  │  (因子调度)     │  │
│  └──────────────┘  └─────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │  Nginx → Cloudflare CDN          │   │
│  │  biga.junwei.fun → :8001         │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

*文档版本: v4.0 | 日期: 2026-05-09*
