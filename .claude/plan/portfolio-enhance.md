# 持仓页面全面增强方案

## 概述

将当前持仓页面从基础版升级为专业量化交易平台级别，覆盖 20+ 项功能，参考同花顺/东方财富/QuantConnect/Interactive Brokers 最佳实践。

## 设计决策

1. **扁平滚动布局** — 不引入子 Tab，通过 `.card` 分组 + 视觉层次管理信息密度
2. **JS 拆分为 6 个模块** — 遵循现有 `Object.assign(App, {...})` 模式
3. **状态管理用内存对象** — `App._pf` 命名空间，不需要 URL 持久化
4. **权益曲线用 Chart.js** — 需叠加基准对比线，LightweightCharts 留给 K 线图
5. **对话框复用现有 `.modal-overlay`** — style.css 已有完整模态框样式

---

## Phase 1: 后端 API 扩展（P0）

### 1.1 数据模型扩展

**文件**: `dashboard/routers/portfolio.py`

#### PositionInfo 新增字段
```python
daily_pnl: float = 0              # 当日盈亏
daily_pnl_pct: float = 0          # 当日盈亏%
position_pct: float = 0           # 持仓占比
entry_date: str = ''              # 建仓日期
holding_days: int = 0             # 持仓天数
stop_loss_price: float = 0        # 止损价
take_profit_price: float = 0      # 止盈价
stop_loss_triggered: bool = False # 止损触发
take_profit_triggered: bool = False
strategy_name: str = ''           # 策略名称
last_action: str = ''             # 最近变动类型
last_action_time: str = ''        # 最近变动时间
cost_amount: float = 0            # 持仓成本
industry: str = ''                # 行业
pre_close: float = 0              # 昨收价
change_pct: float = 0             # 今日涨跌幅
pe_ratio: float = 0               # 市盈率
pb_ratio: float = 0               # 市净率
```

#### PortfolioSnapshot 新增字段
```python
risk: RiskIndicators              # 高级风险指标
benchmark: BenchmarkComparison     # 基准对比
capital: CapitalUtilization        # 资金利用率
stop_loss_alerts: list[StopLossInfo]  # 止损止盈预警
update_time: str = ''             # 快照时间
```

#### 新增 Pydantic 模型
- `RiskIndicators` — VaR95/99、年化波动率、Beta、Alpha、Sortino、Calmar
- `BenchmarkComparison` — 沪深300对比、超额收益、跟踪误差
- `CapitalUtilization` — 资金利用率、现金占比、最大单票占比
- `StopLossInfo` — 止损止盈价格、触发状态
- `TradeRecord`（扩展）— 策略名称、单笔盈亏、佣金、印花税
- `TradeListResponse` — 分页交易记录
- `StrategyGroup` — 按策略分组持仓
- `ClosePositionRequest` / `BulkCloseRequest` — 平仓请求

### 1.2 新增 API 端点

| Method | Path | 功能 |
|--------|------|------|
| POST | `/api/portfolio/close` | 单只/部分平仓 |
| POST | `/api/portfolio/close-all` | 批量/全部平仓 |
| GET | `/api/portfolio/trades/history` | 跨日期分页交易记录 |
| GET | `/api/portfolio/benchmark` | 基准对比（沪深300） |
| GET | `/api/portfolio/capital-utilization` | 资金利用率 |
| GET | `/api/portfolio/risk/advanced` | 高级风险指标 |
| GET | `/api/portfolio/correlation` | 持仓相关性矩阵 |
| GET | `/api/portfolio/strategies` | 多策略持仓分组 |
| GET | `/api/portfolio/search` | 持仓搜索/筛选 |
| GET | `/api/portfolio/export` | 导出 CSV/JSON |
| GET | `/api/portfolio/snapshots` | 历史快照列表 |
| POST | `/api/portfolio/snapshots/save` | 保存当前快照 |

### 1.3 数据存储改造

**`logs/paper/portfolio_state.json`** 新增字段（向后兼容）：
```json
{
  "entry_dates": {"002297": "2026-05-06"},
  "strategies": {"002297": "dual_ma"},
  "stop_losses": {"002297": {"stop_loss": 22.85, "take_profit": 28.87, "trailing_high": 24.50}},
  "position_actions": {"002297": {"action": "new", "time": "2026-05-06T09:35:00"}},
  "daily_start_equity": 50271.80,
  "pre_close_prices": {"002297": 24.10}
}
```

**新增文件**: `logs/paper/portfolio_snapshots.jsonl` — 每日快照归档

### 1.4 现有模块改动

| 文件 | 改动级别 | 说明 |
|------|----------|------|
| `dashboard/routers/portfolio.py` | **重写** | 新模型 + 新端点 + QuoteService 集成 |
| `engine/paper_engine.py` | **中等** | PaperStateManager 追踪 entry_dates/strategies/stop_losses |
| `strategy/base.py` | **小改** | Portfolio dataclass 新增 entry_dates/strategies 字段 |
| `risk/stoploss.py` | **小改** | 暴露 `get_trailing_high()` 方法 |

### 1.5 关键实现逻辑

- **实时行情集成**: 用 QuoteService 替代 DataStorage.get_stock_daily() 获取实时价格
- **高级风险指标**: VaR(参数法)、Sortino(下行标准差)、Calmar(年化收益/最大回撤)
- **基准对比**: 从东方财富获取沪深300 K线，对齐日期计算超额收益
- **相关性矩阵**: 基于日收益率计算两两相关系数
- **平仓操作**: 委托给 PaperEngine._strategy.sell()，通过 pending_orders 机制安全执行

---

## Phase 2: 前端重构（P0）

### 2.1 HTML 结构重写

**文件**: `dashboard/templates/index.html`（第 796-888 行）

#### 统计卡片（3x3 网格 → 9 个）
总资产 | 现金 | 持仓市值 | 持仓数 | 当日盈亏 | 累计收益率 | 最大回撤 | 夏普比率 | 资金利用率

#### 权益曲线（全宽）
- 带时间范围选择器：1月/3月/6月/1年/全部
- 双线叠加：组合收益 + 沪深300基准

#### 图表行（3 列）
持仓盈亏柱状图 | 行业分布饼图 | 市值占比环形图

#### 持仓明细表（14 列 → 增强版）
代码(可点击) | 名称 | 数量 | 均价 | 现价 | 市值 | 盈亏 | 盈亏% | 占比 | 天数 | 止损 | 止盈 | 策略 | 操作
- 底部固定汇总行
- 工具栏：搜索框 + 策略筛选 + 导出 + 快照对比

#### 交易记录（带 Tab 切换）
- 今日交易 Tab
- 历史记录 Tab（日期范围筛选 + 分页）

#### 持仓变动趋势图（全宽）

#### 4 个模态框
- 一键平仓确认（输入代码二次确认）
- 部分平仓（输入数量）
- 止损止盈编辑
- 快照对比（选择两个日期）

### 2.2 JS 模块拆分

| 文件 | 职责 | 预估行数 |
|------|------|----------|
| `portfolio.js` | 编排器：初始化、API 调用、PollManager | ~100 |
| `portfolio-stats.js` | 9 个统计卡片渲染 | ~100 |
| `portfolio-table.js` | 持仓表：排序/搜索/筛选/汇总行/行内操作 | ~350 |
| `portfolio-charts.js` | 5 个图表：权益曲线/盈亏/行业/市值/变动趋势 | ~300 |
| `portfolio-trades.js` | 今日交易 + 历史记录（分页/日期筛选） | ~180 |
| `portfolio-actions.js` | 平仓/止损止盈编辑/导出/快照对比 | ~250 |

### 2.3 CSS 新增样式（~250 行）

- 统计卡颜色语义（`pf-val-up`/`pf-val-down`）
- 工具栏（搜索框/筛选器/按钮组）
- 表格增强（代码链接/策略标签/行内操作按钮/汇总行 sticky）
- 交易记录 Tab 切换
- 分页组件
- 止损止盈视觉指示（触发时红色高亮）
- 快照对比表格
- 响应式断点（1024/768/480px）

### 2.4 交互逻辑

- **排序**: 点击表头排序，支持升序/降序切换
- **搜索**: 实时过滤（代码/名称/策略）
- **策略筛选**: 下拉选择器
- **平仓流程**: 点击"平仓" → 模态框 → 输入代码确认 → POST /api/portfolio/close
- **止损止盈**: 点击价格 → 模态框编辑 → 保存
- **导出**: 点击"导出" → 下载 CSV
- **快照对比**: 选择日期 A/B → 显示持仓差异表格
- **个股跳转**: 点击代码 → 切换到股票详情 Tab

---

## Phase 3: 后端模块改动（P1）

### 3.1 PaperEngine 改造

**文件**: `engine/paper_engine.py`

- `PaperStateManager.__init__`: 新增 `_entry_dates`, `_strategies`, `_stop_losses`, `_position_actions` 字典
- `PaperStateManager.load`: 从 JSON 恢复新字段（向后兼容默认值）
- `PaperStateManager.save`: 持久化新字段 + 每日快照归档
- `PaperEngine._match_orders`: 买入时记录 entry_date/action，卖出时更新 action
- `PaperStateManager.reset_daily_start()`: 开盘时记录 daily_start_equity

### 3.2 Portfolio dataclass 扩展

**文件**: `strategy/base.py`

```python
entry_dates: dict = field(default_factory=dict)    # code -> date_str
strategies: dict = field(default_factory=dict)      # code -> strategy_name
```

### 3.3 StopLoss 暴露接口

**文件**: `risk/stoploss.py`

- 新增 `get_trailing_high(code) -> float` 公开方法

---

## 改动范围评估

| 优先级 | 模块 | 文件 | 改动量 |
|--------|------|------|--------|
| P0 | 后端路由 | `dashboard/routers/portfolio.py` | 重写 ~700 行 |
| P0 | 前端 HTML | `dashboard/templates/index.html` | +300 行 |
| P0 | 前端 JS | `dashboard/static/portfolio*.js` (6个新文件) | +1280 行 |
| P0 | 前端 CSS | `dashboard/static/style.css` | +250 行 |
| P1 | 模拟盘引擎 | `engine/paper_engine.py` | ~100 行改动 |
| P1 | 策略模型 | `strategy/base.py` | ~10 行改动 |
| P1 | 止损模块 | `risk/stoploss.py` | ~15 行改动 |
| P1 | 测试 | `tests/test_dashboard.py` | +200 行 |

**总改动量**: ~2800 行新增/修改

---

## 实施顺序

1. **Step 1**: 后端模型 + API 端点（portfolio.py 重写）
2. **Step 2**: PaperEngine 改造（entry_dates/strategies/stop_losses 追踪）
3. **Step 3**: 前端 HTML 重写（#tab-portfolio section）
4. **Step 4**: 前端 JS 模块拆分 + 实现
5. **Step 5**: CSS 样式新增
6. **Step 6**: 集成测试 + Docker 重建

## 风险点

- `portfolio_state.json` 必须向后兼容，所有新字段用 `.get()` + 默认值
- QuoteService 是单例线程，FastAPI async 访问需确认线程安全（已用 `self._lock`）
- 平仓端点修改运行中引擎状态，通过 pending_orders 机制保证安全
- 前端模块文件必须在 app.js 之前加载
