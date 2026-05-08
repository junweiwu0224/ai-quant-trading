# AI Quant Trading

基于 vnpy 深度定制的 A股量化交易系统，覆盖 **数据采集 → 因子研究 → 策略回测 → 模拟交易 → 实盘交易 → AI 自学习优化** 全流程。

## 功能概览

### 已实现

| 模块 | 功能 |
|------|------|
| 数据层 | AKShare 日K采集、SQLite 存储、自选股管理、每日 16:30 自动同步 |
| 行情服务 | Xueqiu + push2delay 混合行情架构，自动合并行业/板块/概念数据 |
| 策略层 | 双均线/布林带/动量 3 个内置策略 + 自定义策略 CRUD + 参数覆盖 |
| 回测引擎 | 策略回测、收益曲线、月度热力图、回撤曲线、交易明细、多策略对比 |
| AI Alpha | 技术因子库（MA/MACD/RSI/ATR）、LightGBM 模型训练、Optuna 超参优化 |
| 风控模块 | 单票仓位上限、行业集中度、最大回撤止损、日亏损限额 |
| 模拟盘 | PaperEngine 模拟盘、实时行情接入、Dashboard 控制面板 |
| Web 面板 | FastAPI + Jinja2 SPA，8 个 Tab（总览/行情详情/回测/持仓/风控/AI Alpha/模拟盘/策略管理） |
| 自选股管理 | 全量 5000+ 股票搜索、tags 常驻显示、局部更新、行业/板块/概念 enrichment |
| 市场行情 | 实时指数、行业/概念板块 TOP10、涨跌分布、涨跌停统计 |
| 深色模式 | 亮色/深色双主题，localStorage 持久化，支持系统 prefers-color-scheme |
| 搜索组件 | 单选/多选搜索下拉框，搜索内置在下拉中，支持自选股过滤 |
| 响应式布局 | 桌面/平板/手机自适应，侧边栏自动折叠 |

### 待实现

- CTP/XTP BrokerGateway 对接真实券商
- 分钟K线/Tick 数据采集
- 多因子组合策略
- 策略绩效归因分析
- 实盘交易日志 + 对账
- WebSocket 实时风控推送

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11 |
| 引擎 | vnpy 4.3 |
| 数据采集 | AKShare |
| 实时行情 | Xueqiu + push2delay.eastmoney.com |
| 数据库 | SQLite |
| AI/ML | LightGBM, Optuna |
| Web 框架 | FastAPI + Jinja2 |
| 前端 | Vanilla JS + Chart.js v4 + Lightweight Charts |
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
├── strategy/                # 策略层（内置策略 + 管理器）
├── alpha/                   # AI Alpha 层（因子/模型/优化）
├── risk/                    # 风控层（仓位/止损/监控）
├── dashboard/               # Web 面板（FastAPI + 前端）
│   ├── routers/             # API 路由（9 组）
│   ├── static/              # 前端 JS/CSS
│   └── templates/           # HTML 模板
├── engine/                  # vnpy 引擎集成
├── config/                  # 配置
└── docs/                    # 文档（架构设计/优化方案）
```

详见 [架构设计文档](docs/ARCHITECTURE.md)

## License

MIT
