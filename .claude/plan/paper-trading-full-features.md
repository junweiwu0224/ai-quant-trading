# 模拟盘完整功能实现方案

## 一、系统架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Dashboard)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 订单面板 │ │ 持仓明细 │ │ 绩效分析 │ │ 交易历史 │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ K线图表  │ │ 资金曲线 │ │ 风控面板 │ │ 挂单管理 │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 API (FastAPI)                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Paper Trading Router                     │  │
│  │  /api/paper/*                                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 订单管理 │ │ 持仓管理 │ │ 绩效计算 │ │ 历史查询 │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    核心引擎层                                │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │              PaperEngine (增强版)                      │  │
│  │  - 订单撮合 (市价/限价/止损/止盈)                      │  │
│  │  - 持仓管理 (成本计算/浮盈亏)                          │  │
│  │  - 绩效分析 (胜率/夏普/回撤等)                         │  │
│  │  - 风险管理 (止损止盈自动触发)                         │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 订单撮合 │ │ 持仓管理 │ │ 绩效引擎 │ │ 风控引擎 │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    数据存储层                                │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ SQLite   │ │ JSON文件 │ │ 内存缓存 │ │ 日志文件 │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块 | 职责 | 文件位置 |
|------|------|----------|
| **订单管理** | 订单创建、撮合、状态管理 | `engine/order_manager.py` |
| **持仓管理** | 持仓跟踪、成本计算、浮盈亏 | `engine/position_manager.py` |
| **绩效分析** | 收益计算、风险指标、基准对比 | `engine/performance_analyzer.py` |
| **风险管理** | 止损止盈、仓位限制、风险监控 | `engine/risk_manager.py` |
| **交易历史** | 交易记录、查询、导出 | `engine/trade_history.py` |
| **API路由** | RESTful接口 | `dashboard/routers/paper_trading.py` |
| **前端组件** | UI交互、图表展示 | `dashboard/static/paper-trading.js` |

## 二、数据模型设计

### 2.1 SQLite 表结构

```sql
-- 订单表
CREATE TABLE paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    code TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'buy' / 'sell'
    order_type TEXT NOT NULL, -- 'market' / 'limit' / 'stop_loss' / 'take_profit'
    price REAL,               -- 限价/止损价/止盈价
    volume INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',  -- 'pending' / 'filled' / 'partial' / 'cancelled' / 'rejected'
    filled_price REAL,
    filled_volume INTEGER DEFAULT 0,
    commission REAL DEFAULT 0,
    stamp_tax REAL DEFAULT 0,
    slippage REAL DEFAULT 0,
    strategy_name TEXT,
    signal_reason TEXT,       -- 策略信号原因
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 持仓表
CREATE TABLE paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    volume INTEGER NOT NULL,
    avg_price REAL NOT NULL,
    current_price REAL,
    market_value REAL,
    unrealized_pnl REAL,
    unrealized_pnl_pct REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    max_position_pct REAL DEFAULT 0.3,  -- 单只最大仓位占比
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code)
);

-- 交易历史表
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    order_id TEXT,
    code TEXT NOT NULL,
    direction TEXT NOT NULL,
    price REAL NOT NULL,
    volume INTEGER NOT NULL,
    entry_price REAL,         -- 卖出时记录买入均价
    profit REAL,              -- 单笔盈亏
    profit_pct REAL,          -- 盈亏比例
    commission REAL,
    stamp_tax REAL,
    equity_after REAL,        -- 交易后总权益
    strategy_name TEXT,
    signal_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 资金曲线表
CREATE TABLE paper_equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    market_value REAL,
    benchmark_value REAL,     -- 基准指数值
    drawdown REAL,            -- 回撤比例
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 绩效统计表 (每日快照)
CREATE TABLE paper_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    total_equity REAL,
    daily_return REAL,
    cumulative_return REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    win_rate REAL,
    profit_loss_ratio REAL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    avg_win REAL,
    avg_loss REAL,
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- 风控事件表
CREATE TABLE paper_risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,  -- 'stop_loss' / 'take_profit' / 'position_limit' / 'drawdown_limit'
    code TEXT,
    trigger_price REAL,
    action TEXT,               -- 'sell' / 'reject' / 'alert'
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 数据模型 (Python)

```python
# engine/models.py

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional

class OrderType(Enum):
    MARKET = "market"           # 市价单
    LIMIT = "limit"             # 限价单
    STOP_LOSS = "stop_loss"     # 止损单
    TAKE_PROFIT = "take_profit" # 止盈单

class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class PaperOrder:
    """增强版订单"""
    order_id: str
    code: str
    direction: Direction
    order_type: OrderType
    price: Optional[float] = None  # 限价/止损价/止盈价
    volume: int = 0
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_volume: int = 0
    commission: float = 0
    stamp_tax: float = 0
    slippage: float = 0
    strategy_name: Optional[str] = None
    signal_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

@dataclass
class PaperPosition:
    """增强版持仓"""
    code: str
    volume: int
    avg_price: float
    current_price: float = 0
    market_value: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    max_position_pct: float = 0.3
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

@dataclass
class PaperTrade:
    """增强版交易记录"""
    trade_id: str
    order_id: Optional[str]
    code: str
    direction: Direction
    price: float
    volume: int
    entry_price: float = 0
    profit: float = 0
    profit_pct: float = 0
    commission: float = 0
    stamp_tax: float = 0
    equity_after: float = 0
    strategy_name: Optional[str] = None
    signal_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_equity: float
    daily_return: float
    cumulative_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    alpha: float
    beta: float
    information_ratio: float

@dataclass
class EquityCurvePoint:
    """资金曲线点"""
    timestamp: datetime
    equity: float
    cash: float
    market_value: float
    benchmark_value: Optional[float] = None
    drawdown: float = 0

@dataclass
class RiskEvent:
    """风控事件"""
    event_type: str
    code: Optional[str]
    trigger_price: Optional[float]
    action: str
    reason: str
    created_at: datetime = field(default_factory=datetime.now)
```

## 三、API 接口设计

### 3.1 订单管理 API

```python
# dashboard/routers/paper_trading.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date

router = APIRouter(prefix="/api/paper", tags=["paper-trading"])

# ────────────── 请求模型 ──────────────

class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    code: str = Field(..., description="股票代码")
    direction: str = Field(..., description="buy/sell")
    order_type: str = Field(default="market", description="market/limit/stop_loss/take_profit")
    price: Optional[float] = Field(None, description="限价/止损价/止盈价")
    volume: int = Field(..., gt=0, description="数量")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    signal_reason: Optional[str] = Field(None, description="信号原因")

class UpdateStopLossRequest(BaseModel):
    """更新止损止盈请求"""
    code: str
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

class BatchOrderRequest(BaseModel):
    """批量订单请求"""
    orders: List[CreateOrderRequest]

# ────────────── 订单 API ──────────────

@router.post("/orders")
async def create_order(req: CreateOrderRequest):
    """创建订单（市价/限价/止损/止盈）"""
    pass

@router.get("/orders")
async def get_orders(
    status: Optional[str] = Query(None, description="订单状态筛选"),
    code: Optional[str] = Query(None, description="股票代码筛选"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    """获取订单列表"""
    pass

@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """获取订单详情"""
    pass

@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """撤销订单"""
    pass

@router.post("/orders/batch")
async def create_batch_orders(req: BatchOrderRequest):
    """批量创建订单"""
    pass

# ────────────── 持仓 API ──────────────

@router.get("/positions")
async def get_positions():
    """获取当前持仓列表"""
    pass

@router.get("/positions/{code}")
async def get_position(code: str):
    """获取单只股票持仓详情"""
    pass

@router.put("/positions/{code}/stop-loss")
async def update_stop_loss(code: str, req: UpdateStopLossRequest):
    """更新止损止盈价格"""
    pass

@router.post("/positions/{code}/close")
async def close_position(code: str, volume: Optional[int] = None):
    """平仓（全部或部分）"""
    pass

# ────────────── 绩效 API ──────────────

@router.get("/performance")
async def get_performance(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """获取绩效统计"""
    pass

@router.get("/performance/daily")
async def get_daily_performance(
    days: int = Query(30, ge=1, le=365)
):
    """获取每日绩效历史"""
    pass

@router.get("/performance/benchmark")
async def get_benchmark_comparison(
    benchmark: str = Query("000300", description="基准指数代码"),
    days: int = Query(30, ge=1, le=365)
):
    """获取基准对比数据"""
    pass

# ────────────── 资金曲线 API ──────────────

@router.get("/equity-curve")
async def get_equity_curve(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    interval: str = Query("1d", description="1m/5m/15m/1h/1d")
):
    """获取资金曲线"""
    pass

@router.get("/drawdown")
async def get_drawdown_curve(
    days: int = Query(30, ge=1, le=365)
):
    """获取回撤曲线"""
    pass

# ────────────── 交易历史 API ──────────────

@router.get("/trades")
async def get_trades(
    code: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    """获取交易历史"""
    pass

@router.get("/trades/stats")
async def get_trade_stats(
    days: int = Query(30, ge=1, le=365)
):
    """获取交易统计"""
    pass

@router.get("/trades/export")
async def export_trades(
    format: str = Query("csv", description="csv/pdf"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """导出交易记录"""
    pass

# ────────────── 风控 API ──────────────

@router.get("/risk/events")
async def get_risk_events(
    event_type: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365)
):
    """获取风控事件"""
    pass

@router.get("/risk/rules")
async def get_risk_rules():
    """获取风控规则配置"""
    pass

@router.put("/risk/rules")
async def update_risk_rules(rules: dict):
    """更新风控规则"""
    pass

# ────────────── 模拟盘控制 API ──────────────

@router.post("/start")
async def start_paper_trading(config: dict):
    """启动模拟盘"""
    pass

@router.post("/stop")
async def stop_paper_trading():
    """停止模拟盘"""
    pass

@router.post("/reset")
async def reset_paper_trading(confirm: bool = False):
    """重置模拟盘"""
    pass

@router.get("/status")
async def get_paper_status():
    """获取模拟盘状态"""
    pass

@router.get("/config")
async def get_paper_config():
    """获取模拟盘配置"""
    pass

@router.put("/config")
async def update_paper_config(config: dict):
    """更新模拟盘配置"""
    pass
```

### 3.2 API 响应格式

```python
# 统一响应格式
{
    "success": true,
    "data": { ... },
    "message": "操作成功",
    "timestamp": "2026-05-07T12:00:00Z"
}

# 分页响应格式
{
    "success": true,
    "data": {
        "items": [ ... ],
        "total": 100,
        "page": 1,
        "page_size": 50,
        "total_pages": 2
    }
}

# 错误响应格式
{
    "success": false,
    "error": {
        "code": "INSUFFICIENT_FUNDS",
        "message": "资金不足",
        "details": { ... }
    }
}
```

## 四、前端组件设计

### 4.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│                    模拟盘控制面板                             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 状态栏: 运行状态 | 总资产 | 当日盈亏 | 持仓数 | 交易数 │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────────────┐  ┌────────────────────────────┐   │
│  │                    │  │                            │   │
│  │    订单面板        │  │      K线图表               │   │
│  │  ┌──────────────┐  │  │   (LightweightCharts)     │   │
│  │  │ 买入/卖出    │  │  │                            │   │
│  │  │ 市价/限价    │  │  │                            │   │
│  │  │ 止损/止盈    │  │  │                            │   │
│  │  └──────────────┘  │  │                            │   │
│  │  ┌──────────────┐  │  │                            │   │
│  │  │ 快捷按钮     │  │  │                            │   │
│  │  │ 100/500/1000 │  │  │                            │   │
│  │  └──────────────┘  │  │                            │   │
│  │                    │  │                            │   │
│  └────────────────────┘  └────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    持仓明细表                         │  │
│  │  代码 | 名称 | 数量 | 成本 | 现价 | 浮盈亏 | 仓位%  │  │
│  │  ─────────────────────────────────────────────────   │  │
│  │  600000 | 浦发银行 | 1000 | 10.50 | 10.80 | +300    │  │
│  │  止损: 10.00 | 止盈: 11.50 | [设置] [平仓]          │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────────────┐  ┌────────────────────────────┐   │
│  │    挂单管理        │  │      绩效统计              │   │
│  │  订单ID | 代码     │  │  胜率: 65%                │   │
│  │  类型 | 价格       │  │  盈亏比: 1.8              │   │
│  │  数量 | 状态       │  │  夏普比率: 1.2            │   │
│  │  [撤销]           │  │  最大回撤: -8.5%          │   │
│  └────────────────────┘  └────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    资金曲线                           │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  资金走势 + 基准对比 + 回撤区间               │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  月度收益热力图 | 收益分布直方图 | 星期效应         │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    交易历史                           │  │
│  │  时间 | 代码 | 方向 | 价格 | 数量 | 盈亏 | 原因     │  │
│  │  [筛选] [导出CSV] [导出PDF]                          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 组件清单

| 组件 | 功能 | 优先级 |
|------|------|--------|
| **OrderPanel** | 订单创建面板（市价/限价/止损/止盈） | P0 |
| **PositionTable** | 持仓明细表（含止损止盈设置） | P0 |
| **OrderBook** | 挂单管理（查看/撤销） | P0 |
| **PerformanceStats** | 绩效统计面板 | P0 |
| **EquityCurve** | 资金曲线图表（含基准对比） | P0 |
| **DrawdownChart** | 回撤曲线图表 | P1 |
| **TradeHistory** | 交易历史（筛选/导出） | P1 |
| **MonthlyHeatmap** | 月度收益热力图 | P1 |
| **ReturnDistribution** | 收益分布直方图 | P2 |
| **WeekdayEffect** | 星期效应分析 | P2 |
| **RiskPanel** | 风控事件面板 | P2 |
| **StrategySignals** | 策略信号可视化 | P3 |

### 4.3 交互流程

```
用户操作流程：

1. 启动模拟盘
   ├── 配置策略、股票、资金
   ├── 点击"启动"
   └── 状态栏显示"运行中"

2. 手动下单
   ├── 选择股票代码
   ├── 选择订单类型（市价/限价/止损/止盈）
   ├── 输入价格和数量
   ├── 点击"买入"或"卖出"
   └── 订单提交到挂单列表

3. 持仓管理
   ├── 查看持仓明细
   ├── 设置止损止盈价格
   ├── 部分平仓或全部平仓
   └── 实时更新浮盈亏

4. 绩效分析
   ├── 查看胜率、盈亏比、夏普比率
   ├── 对比基准指数
   ├── 分析月度收益热力图
   └── 导出绩效报告

5. 交易历史
   ├── 按日期/股票/方向筛选
   ├── 查看每笔交易详情
   ├── 导出CSV/PDF
   └── 分析交易统计
```

### 4.4 状态管理

```javascript
// 前端状态管理方案

const PaperTrading = {
    // 状态
    state: {
        isRunning: false,
        config: {},
        positions: [],
        orders: [],
        trades: [],
        performance: {},
        equityCurve: [],
        riskEvents: []
    },

    // 轮询策略
    polling: {
        status: { interval: 5000, timer: null },      // 状态刷新
        positions: { interval: 10000, timer: null },   // 持仓刷新
        orders: { interval: 3000, timer: null },       // 挂单刷新
        equity: { interval: 30000, timer: null },      // 资金曲线
    },

    // 缓存策略
    cache: {
        trades: { data: null, timestamp: 0, ttl: 60000 },
        performance: { data: null, timestamp: 0, ttl: 30000 },
    },

    // WebSocket (可选)
    ws: null,
    initWebSocket() {
        // 实时推送持仓变化、订单成交
    }
};
```

## 五、核心功能实现

### 5.1 订单管理系统

```python
# engine/order_manager.py

class OrderManager:
    """订单管理器"""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_db()

    def create_order(self, order: PaperOrder) -> PaperOrder:
        """创建订单"""
        # 1. 验证订单参数
        self._validate_order(order)

        # 2. 检查资金/持仓
        if order.direction == Direction.LONG:
            self._check_buy_power(order)
        else:
            self._check_position(order)

        # 3. 保存到数据库
        self._save_order(order)

        # 4. 如果是市价单，立即撮合
        if order.order_type == OrderType.MARKET:
            return self._execute_market_order(order)

        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        """撤销订单"""
        order = self._get_order(order_id)
        if order.status != OrderStatus.PENDING:
            raise ValueError(f"订单状态不允许撤销: {order.status}")

        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now()
        self._update_order(order)
        return order

    def get_pending_orders(self, code: str = None) -> List[PaperOrder]:
        """获取待撮合订单"""
        pass

    def match_orders(self, quotes: dict) -> List[PaperTrade]:
        """撮合订单"""
        pending = self.get_pending_orders()
        trades = []

        for order in pending:
            quote = quotes.get(order.code)
            if not quote:
                continue

            # 检查是否触发撮合条件
            if self._should_match(order, quote):
                trade = self._execute_order(order, quote)
                if trade:
                    trades.append(trade)

        return trades

    def _should_match(self, order: PaperOrder, quote) -> bool:
        """判断是否应该撮合"""
        if order.order_type == OrderType.MARKET:
            return True
        elif order.order_type == OrderType.LIMIT:
            if order.direction == Direction.LONG:
                return quote.price <= order.price
            else:
                return quote.price >= order.price
        elif order.order_type == OrderType.STOP_LOSS:
            return quote.price <= order.price
        elif order.order_type == OrderType.TAKE_PROFIT:
            return quote.price >= order.price
        return False
```

### 5.2 绩效分析引擎

```python
# engine/performance_analyzer.py

import numpy as np
from typing import List, Dict
from datetime import datetime, date

class PerformanceAnalyzer:
    """绩效分析器"""

    def __init__(self, trades: List[PaperTrade], equity_curve: List[EquityCurvePoint]):
        self.trades = trades
        self.equity_curve = equity_curve

    def calculate_metrics(self, benchmark_returns: List[float] = None) -> PerformanceMetrics:
        """计算完整绩效指标"""
        returns = self._calculate_daily_returns()

        metrics = PerformanceMetrics(
            total_equity=self.equity_curve[-1].equity if self.equity_curve else 0,
            daily_return=returns[-1] if returns else 0,
            cumulative_return=self._calc_cumulative_return(returns),
            max_drawdown=self._calc_max_drawdown(),
            sharpe_ratio=self._calc_sharpe_ratio(returns),
            sortino_ratio=self._calc_sortino_ratio(returns),
            calmar_ratio=self._calc_calmar_ratio(returns),
            win_rate=self._calc_win_rate(),
            profit_loss_ratio=self._calc_profit_loss_ratio(),
            total_trades=len(self.trades),
            winning_trades=self._count_winning_trades(),
            losing_trades=self._count_losing_trades(),
            avg_win=self._calc_avg_win(),
            avg_loss=self._calc_avg_loss(),
            max_consecutive_wins=self._calc_max_consecutive(True),
            max_consecutive_losses=self._calc_max_consecutive(False),
            alpha=self._calc_alpha(returns, benchmark_returns) if benchmark_returns else 0,
            beta=self._calc_beta(returns, benchmark_returns) if benchmark_returns else 0,
            information_ratio=self._calc_information_ratio(returns, benchmark_returns) if benchmark_returns else 0
        )

        return metrics

    def get_monthly_returns(self) -> Dict[str, float]:
        """获取月度收益"""
        monthly = {}
        for point in self.equity_curve:
            month_key = point.timestamp.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = point.equity
            else:
                monthly[month_key] = point.equity
        return monthly

    def get_return_distribution(self, bins: int = 20) -> Dict:
        """获取收益分布"""
        returns = self._calculate_daily_returns()
        hist, edges = np.histogram(returns, bins=bins)
        return {
            "counts": hist.tolist(),
            "edges": edges.tolist()
        }

    def get_weekday_effect(self) -> Dict[str, float]:
        """获取星期效应"""
        weekday_returns = {i: [] for i in range(5)}
        for point in self.equity_curve:
            weekday = point.timestamp.weekday()
            if weekday < 5:
                weekday_returns[weekday].append(point.equity)

        return {
            "周一": np.mean(weekday_returns[0]),
            "周二": np.mean(weekday_returns[1]),
            "周三": np.mean(weekday_returns[2]),
            "周四": np.mean(weekday_returns[3]),
            "周五": np.mean(weekday_returns[4])
        }

    def _calc_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.03) -> float:
        """计算夏普比率"""
        if not returns:
            return 0
        excess_returns = np.array(returns) - risk_free_rate / 252
        if np.std(excess_returns) == 0:
            return 0
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

    def _calc_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.equity_curve:
            return 0
        equities = [p.equity for p in self.equity_curve]
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _calc_win_rate(self) -> float:
        """计算胜率"""
        if not self.trades:
            return 0
        winning = sum(1 for t in self.trades if t.profit > 0)
        return winning / len(self.trades)

    def _calc_profit_loss_ratio(self) -> float:
        """计算盈亏比"""
        wins = [t.profit for t in self.trades if t.profit > 0]
        losses = [abs(t.profit) for t in self.trades if t.profit < 0]
        if not wins or not losses:
            return 0
        return np.mean(wins) / np.mean(losses)
```

### 5.3 风险管理器

```python
# engine/risk_manager.py

class RiskManager:
    """风险管理器"""

    def __init__(self, config: dict):
        self.config = config
        self.events: List[RiskEvent] = []

    def check_position_limit(self, code: str, volume: int, price: float,
                            portfolio: Portfolio, prices: dict) -> tuple[bool, str]:
        """检查仓位限制"""
        # 单只股票最大仓位占比
        max_pct = self.config.get("max_position_pct", 0.3)
        current_value = portfolio.get_market_value(prices)
        new_value = volume * price
        total_equity = portfolio.get_total_equity(prices)

        if (current_value + new_value) / total_equity > max_pct:
            return False, f"超过单只最大仓位限制({max_pct*100}%)"

        # 最大持仓数量
        max_positions = self.config.get("max_positions", 10)
        if len(portfolio.positions) >= max_positions and code not in portfolio.positions:
            return False, f"超过最大持仓数量限制({max_positions}只)"

        return True, ""

    def check_drawdown_limit(self, current_equity: float, peak_equity: float) -> tuple[bool, str]:
        """检查回撤限制"""
        max_drawdown = self.config.get("max_drawdown", 0.2)
        drawdown = (peak_equity - current_equity) / peak_equity

        if drawdown >= max_drawdown:
            return False, f"触发最大回撤限制({max_drawdown*100}%)"

        return True, ""

    def check_stop_loss(self, position: PaperPosition, current_price: float) -> Optional[RiskEvent]:
        """检查止损"""
        if position.stop_loss_price and current_price <= position.stop_loss_price:
            return RiskEvent(
                event_type="stop_loss",
                code=position.code,
                trigger_price=current_price,
                action="sell",
                reason=f"触发止损: 当前价{current_price} <= 止损价{position.stop_loss_price}"
            )
        return None

    def check_take_profit(self, position: PaperPosition, current_price: float) -> Optional[RiskEvent]:
        """检查止盈"""
        if position.take_profit_price and current_price >= position.take_profit_price:
            return RiskEvent(
                event_type="take_profit",
                code=position.code,
                trigger_price=current_price,
                action="sell",
                reason=f"触发止盈: 当前价{current_price} >= 止盈价{position.take_profit_price}"
            )
        return None

    def check_daily_loss_limit(self, daily_pnl: float, total_equity: float) -> tuple[bool, str]:
        """检查单日亏损限制"""
        max_daily_loss = self.config.get("max_daily_loss", 0.05)
        if daily_pnl < 0 and abs(daily_pnl) / total_equity >= max_daily_loss:
            return False, f"触发单日亏损限制({max_daily_loss*100}%)"
        return True, ""
```

## 六、实现步骤

### 6.1 Phase 1: 核心功能 (P0)

**目标**: 实现基本的订单管理和持仓管理

| 任务 | 文件 | 说明 |
|------|------|------|
| 1.1 | `engine/models.py` | 创建数据模型 |
| 1.2 | `engine/order_manager.py` | 实现订单管理器 |
| 1.3 | `engine/position_manager.py` | 增强持仓管理器 |
| 1.4 | `dashboard/routers/paper_trading.py` | 实现订单API |
| 1.5 | `dashboard/static/paper-trading.js` | 订单面板UI |
| 1.6 | `dashboard/static/paper-trading.js` | 持仓明细表UI |

**预计工时**: 3-4天

### 6.2 Phase 2: 绩效分析 (P1)

**目标**: 实现完整的绩效统计和资金曲线

| 任务 | 文件 | 说明 |
|------|------|------|
| 2.1 | `engine/performance_analyzer.py` | 实现绩效分析器 |
| 2.2 | `engine/trade_history.py` | 增强交易历史 |
| 2.3 | `dashboard/routers/paper_trading.py` | 绩效API |
| 2.4 | `dashboard/static/paper-trading.js` | 绩效统计面板 |
| 2.5 | `dashboard/static/paper-trading.js` | 资金曲线图表 |
| 2.6 | `dashboard/static/paper-trading.js` | 回撤曲线图表 |

**预计工时**: 2-3天

### 6.3 Phase 3: 高级功能 (P2)

**目标**: 实现高级分析和风控功能

| 任务 | 文件 | 说明 |
|------|------|------|
| 3.1 | `engine/risk_manager.py` | 增强风险管理器 |
| 3.2 | `dashboard/routers/paper_trading.py` | 风控API |
| 3.3 | `dashboard/static/paper-trading.js` | 月度热力图 |
| 3.4 | `dashboard/static/paper-trading.js` | 收益分布图 |
| 3.5 | `dashboard/static/paper-trading.js` | 星期效应分析 |
| 3.6 | `dashboard/static/paper-trading.js` | 风控事件面板 |

**预计工时**: 2-3天

### 6.4 Phase 4: 体验优化 (P3)

**目标**: 完善用户体验和导出功能

| 任务 | 文件 | 说明 |
|------|------|------|
| 4.1 | `engine/export.py` | CSV/PDF导出 |
| 4.2 | `dashboard/static/paper-trading.js` | 交易历史筛选 |
| 4.3 | `dashboard/static/paper-trading.js` | 策略信号可视化 |
| 4.4 | `dashboard/static/paper-trading.js` | 实时K线集成 |
| 4.5 | `dashboard/static/paper-trading.js` | 响应式优化 |

**预计工时**: 2天

## 七、技术要点

### 7.1 数据库选择

- **SQLite**: 适合单机部署，轻量级
- **表设计**: 使用索引优化查询性能
- **备份**: 定期备份数据库文件

### 7.2 实时性

- **轮询策略**: 不同数据使用不同刷新频率
- **WebSocket**: 可选，用于实时推送持仓变化
- **缓存**: 缓存不常变化的数据（绩效统计）

### 7.3 性能优化

- **分页查询**: 交易历史使用分页
- **索引优化**: 为常用查询字段创建索引
- **异步处理**: 耗时操作使用异步

### 7.4 安全考虑

- **输入验证**: 所有用户输入进行验证
- **SQL注入**: 使用参数化查询
- **XSS防护**: 输出时进行HTML转义

## 八、测试计划

### 8.1 单元测试

- 订单管理器测试
- 绩效分析器测试
- 风险管理器测试

### 8.2 集成测试

- API接口测试
- 数据库操作测试
- 前后端联调测试

### 8.3 E2E测试

- 完整下单流程测试
- 持仓管理流程测试
- 绩效分析流程测试

## 九、部署方案

### 9.1 数据库迁移

```bash
# 创建数据库表
python -m engine.migrate

# 导入历史数据（可选）
python -m engine.import_history
```

### 9.2 配置更新

```python
# config/settings.py

PAPER_TRADING_CONFIG = {
    "db_path": "data/paper_trading.db",
    "max_position_pct": 0.3,
    "max_positions": 10,
    "max_drawdown": 0.2,
    "max_daily_loss": 0.05,
    "default_commission": 0.0003,
    "default_stamp_tax": 0.001,
    "default_slippage": 0.002
}
```

### 9.3 Docker 更新

```dockerfile
# Dockerfile 添加数据库初始化
RUN python -m engine.migrate
```

## 十、预期效果

### 10.1 功能完整性

- ✅ 完整的订单管理（市价/限价/止损/止盈）
- ✅ 详细的持仓明细（成本/浮盈亏/止损止盈）
- ✅ 专业的绩效分析（胜率/夏普/回撤等）
- ✅ 丰富的图表展示（资金曲线/热力图/分布图）
- ✅ 完善的风控管理（止损止盈/仓位限制）
- ✅ 便捷的导出功能（CSV/PDF）

### 10.2 用户体验

- ✅ 直观的操作界面
- ✅ 实时的数据更新
- ✅ 流畅的交互体验
- ✅ 完善的错误提示

### 10.3 系统稳定性

- ✅ 数据持久化存储
- ✅ 异常处理完善
- ✅ 日志记录完整
- ✅ 备份恢复机制

---

**总结**: 本方案设计了一个功能完整、专业级的股票交易模拟盘系统，涵盖了订单管理、持仓管理、绩效分析、风险管理等核心功能，并提供了丰富的图表展示和导出功能。通过分阶段实施，可以逐步构建出一个功能最全的模拟盘系统。
