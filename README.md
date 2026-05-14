# AI Quant Trading

基于 vnpy 深度定制的 A股量化交易系统，覆盖 **数据采集 → 因子研究 → 策略回测 → 模拟交易 → AI 自学习优化** 全流程。

## 功能概览

### 已实现

| 模块 | 功能 |
|------|------|
| **数据层** | AKShare 日K采集、SQLite 存储、自选股管理、每日 16:30 自动同步 |
| **行情服务** | Xueqiu + push2delay + 腾讯 fqkline 混合行情架构，自动合并行业/板块/概念/财务指标 |
| **策略层** | 双均线/布林带/动量 3 个内置策略 + 自定义策略 CRUD + 参数覆盖 + 策略版本管理（保存/回滚/Diff） |
| **回测引擎** | 策略回测、收益曲线、月度热力图、回撤曲线、交易明细、多策略对比、Monte Carlo 模拟、Walk-Forward 分析、Brinson 归因、PDF 报告 |
| **AI Alpha** | 技术因子库 30+、基本面因子（代理+真实财务）、LightGBM+XGBoost 集成模型、Optuna 超参优化、SHAP 可解释性、因子挖掘、跨截面选股 |
| **资金流因子** | 北向资金持股比例/连续净买入、龙虎榜机构净买入/热度评分 |
| **情绪因子** | 新闻/公告情绪分析（SnowNLP + 关键词降级）、3/5 日均值、变化率 |
| **宏观因子** | SHIBOR/国债收益率/M2 增速/社融规模，全市场统一赋值 |
| **因子调度器** | 交易时段高频更新（北向 15min/板块 30min/情绪 1h/宏观日更），盘后降频 |
| **条件选股** | 条件过滤引擎（字段+运算符+值）、6 预设策略、CSV 导出、一键加入自选股 |
| **AI 选股** | 跨截面模型训练→TOP N 推荐、风险评分、SHAP 因子贡献、策略收益曲线 |
| **预警系统** | 7 种条件（价格/涨跌幅/量比/换手率/振幅）、防重复触发、WebSocket 实时推送 |
| **筹码分布** | 基于 K 线成交量+换手率估算、获利比例/平均成本/90% 集中度 |
| **多周期共振** | 日/周/月三周期 MA/RSI/MACD 信号共振分析、强度评分 |
| **龙虎榜分析** | 东方财富龙虎榜接入、营业部画像 TOP15、上榜后收益统计 |
| **研报整合** | 东方财富研报列表、LLM 自动解读核心观点/风险/建议 |
| **策略导入导出** | JSON 格式导入导出、版本对比、覆盖/跳过同名策略 |
| **市场雷达** | 涨跌幅/振幅/换手率/量比 TOP10、板块轮动排名、板块热力图、北向资金净流入 |
| **风控模块** | 单票仓位上限、行业集中度、最大回撤止损、日亏损限额、ATR 止损、跟踪止损 |
| **模拟盘** | PaperEngine 模拟盘、市价/限价/止损/止盈单、实时行情接入、Dashboard 控制面板 |
| **持仓管理** | 持仓监控、风险指标（VaR/Sharpe/Sortino/Calmar）、行业分布、相关性矩阵、导出 |
| **LLM 集成** | gpt-5.5 大模型、自然语言策略生成、AI 结果解读、流式对话 |
| **多股对比** | 最多 5 只股票归一化收益率对比，支持缩放/滚动/区间标注 |
| **画线工具** | 趋势线/水平线/斐波那契回撤线，保存/加载/删除 |
| **多周期切换** | 1m/5m/15m/30m/60m/日/周/月 K 线 |
| **Web 面板** | FastAPI + Jinja2 SPA，5+1 导航（监控/情报/研发/交易/模拟+AI助手），130+ API 端点，Command Palette/隐私模式/实验快照 |
| **深色模式** | 亮色/深色双主题，localStorage 持久化 |
| **响应式布局** | 桌面/平板/手机自适应，侧边栏自动折叠 |

### 竞品对标改进（已完成）

对标通达信、QMT、PTrade、AI涨乐、同花顺iQuant 等竞品分析后实现的改进：

| 功能 | 对标 | 状态 |
|------|------|------|
| 板块热力图 | 同花顺 | ✅ 行业×涨跌幅色块 treemap 可视化，红涨绿跌色阶 |
| 多周期共振信号 | 通达信 | ✅ 日/周/月三周期 MA/RSI/MACD 信号共振分析 |
| 分时图增强 | 通达信 | ✅ 量比实时显示、均价线、多日分时叠加对比 |
| 龙虎榜深度分析 | 东方财富 Choice | ✅ 营业部画像、上榜记录、3日上涨概率、收益统计 |
| 策略导入导出 | 通达信公式社区 | ✅ JSON 导入导出、版本对比、覆盖/跳过同名 |
| 研报整合+LLM解读 | 东方财富 Choice | ✅ 东方财富研报接入、AI 自动解读核心观点+风险 |

### 待开发

| 功能 | 对标 | 说明 |
|------|------|------|
| 公式系统 | 通达信 | 类通达信语法公式引擎，支持自定义指标/选股公式 |
| 条件单 | QMT/PTrade | 预警触发后自动下单（止盈止损/拐点/回落卖出） |
| 篮子交易 | QMT/PTrade | AI 选股 TOP20 一键组合买入，按等权/风险平价分配 |
| 移动端 PWA | 涨乐财富通 | PWA + 离线缓存 + 推送通知 |
| Tick 级回测 | QMT | 分钟级/Tick 级回测引擎，支持日内策略 |
| L2 十档行情 | QMT/PTrade | 十档买卖盘、逐笔成交、委托队列 |
| 实盘交易 | QMT/PTrade | CTP/XTP BrokerGateway 对接真实券商 |

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11 |
| 引擎 | vnpy 4.3 |
| 数据采集 | AKShare |
| 实时行情 | Xueqiu + push2delay + 腾讯 fqkline |
| 数据库 | SQLite |
| AI/ML | LightGBM, XGBoost, Optuna, SHAP |
| NLP | SnowNLP, gpt-5.5 (LLM) |
| Web 框架 | FastAPI + Jinja2 |
| 前端 | Vanilla JS + Chart.js v4 + KlineCharts v9 |
| 任务调度 | APScheduler |
| 容器化 | Docker + docker-compose |

## 快速开始

```bash
# 克隆项目
git clone https://github.com/junweiwu0224/ai-quant-trading.git
cd ai-quant-trading

# Docker 部署
docker compose up -d

# 访问
open http://localhost:8001
```

## 项目结构

```
quant-trading-system/
├── data/                    # 数据层（采集/存储/调度/行情服务）
│   ├── collector/           # 数据采集（AKShare）+ 实时行情（quote_service.py）
│   ├── storage/             # SQLite 存储管理
│   └── scheduler/           # 定时任务调度
├── strategy/                # 策略层（内置策略 + 管理器 + 版本管理）
├── alpha/                   # AI Alpha 层
│   ├── factors/             # 因子库（技术/基本面/资金流/情绪/宏观）
│   ├── models/              # 模型（LightGBM/XGBoost/Ensemble）
│   ├── feature_pipeline.py  # 特征工程管道
│   ├── cross_sectional.py   # 跨截面选股模型
│   ├── backtest.py          # 组合回测引擎
│   ├── screener.py          # 条件选股引擎
│   ├── llm_client.py        # LLM 客户端（OpenAI 兼容）
│   ├── nl_strategy.py       # 自然语言策略生成
│   └── factor_scheduler.py  # 因子动态更新调度器
├── risk/                    # 风控层（仓位/止损/监控）
├── dashboard/               # Web 面板（FastAPI + 前端）
│   ├── routers/             # API 路由（17 组，120+ 端点）
│   ├── static/              # 前端 JS/CSS（35+ 模块，含信号聚合/三态切换/离线指示等）
│   └── templates/           # HTML 模板
├── engine/                  # 引擎集成（回测/模拟盘/实盘/预警/报告）
├── config/                  # 配置
└── docs/                    # 文档（架构设计）
```

详见 [架构设计文档](docs/ARCHITECTURE.md)

## License

MIT
