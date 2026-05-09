# 股票行情页面终极实现方案

## 目标
打造对标东方财富/同花顺的专业级股票行情页面，覆盖技术分析、基本面分析、资金面分析全链路。

---

## 现状盘点

### 已有功能 ✅
| 模块 | 功能 | 状态 |
|------|------|------|
| 行情数据 | 价格、涨跌、成交量、成交额、换手率、振幅、量比 | ✅ |
| K线图 | 日K/周K/月K/60分/15分/5分 + MA均线(5/10/20/60) | ✅ |
| 分时图 | 当日分时 + 均价线 + 昨收参考线 | ✅ |
| 五档盘口 | 买卖五档价格和数量 | ✅ |
| 资金流向 | 主力净流入 + 超大单（近20日） | ✅ |
| 专业指标 | 52周高低、平均成交量(5d/10d) | ✅ |
| 财务指标 | EPS、BPS、营收、净利润、毛利率、净利率、ROE、负债率 | ✅ |
| 估值指标 | PE、PB、PE_TTM、PS、总市值、流通市值 | ✅ |
| 股本信息 | 总股本、流通股本 | ✅ |
| 搜索 | 全量A股搜索（5500+只） | ✅ |

### 缺失功能 ❌
| 模块 | 功能 | 对标 |
|------|------|------|
| 技术指标 | MACD/KDJ/RSI/BOLL/WR/OBV | 东方财富 |
| 阶段涨幅 | 5日/20日/60日/年初至今涨幅 | 东方财富 |
| 内外盘 | 内盘/外盘数量和比例 | 东方财富 |
| 涨跌停价 | 涨停价、跌停价 | 东方财富 |
| 公告信息 | 最近公告列表 | 东方财富 |
| 股东研究 | 十大股东、机构持仓 | 东方财富 |
| 分红历史 | 历次分红送转记录 | 东方财富 |
| 利润趋势 | 近8季度营收/净利润折线图 | 东方财富 |
| 行业对比 | 同行业PE/PB/ROE横向对比 | 东方财富 |
| 北向资金 | 沪深港通持仓 | 东方财富 |
| 筹码分布 | 成本分布图 | 同花顺 |
| 新闻资讯 | 公司/行业新闻 | 东方财富 |
| 研报 | 券商研报评级 | 东方财富 |
| 龙虎榜 | 游资/机构席位 | 东方财富 |
| 融资融券 | 两融余额 | 东方财富 |

---

## 实现方案（分3期）

### 第1期：技术分析增强（核心交易功能）

#### 1.1 技术指标系统
**目标**：K线图支持 MACD/KDJ/RSI/BOLL/WR/OBV 六大技术指标

**数据源**：复用现有 K 线数据（`/api/stock/kline/{code}`），前端计算指标值

**前端实现**：
```javascript
// 技术指标计算引擎（纯前端）
const TechnicalIndicators = {
    MACD(closes, fast=12, slow=26, signal=9) {
        const emaFast = this.EMA(closes, fast);
        const emaSlow = this.EMA(closes, slow);
        const dif = emaFast.map((v, i) => v - emaSlow[i]);
        const dea = this.EMA(dif, signal);
        const macd = dif.map((v, i) => (v - dea[i]) * 2);
        return { dif, dea, macd };
    },
    KDJ(highs, lows, closes, period=9) { /* KDJ计算 */ },
    RSI(closes, period=14) { /* RSI计算 */ },
    BOLL(closes, period=20, multiplier=2) { /* 布林带计算 */ },
    WR(highs, lows, closes, period=14) { /* 威廉指标 */ },
    OBV(closes, volumes) { /* 能量潮 */ },
};
```

**UI设计**：
- K线图下方增加副图区域（高度120px），显示 MACD/KDJ/RSI
- 图表 tab 栏增加指标选择器（下拉菜单）
- 支持主图叠加（BOLL）和副图分离（MACD/KDJ/RSI）

**LightweightCharts 实现**：
```javascript
// MACD 副图用 HistogramSeries + LineSeries
const macdSeries = chart.addHistogramSeries({
    priceScaleId: 'macd',
    // ...
});
const difSeries = chart.addLineSeries({
    priceScaleId: 'macd',
    // ...
});
```

#### 1.2 阶段涨幅
**数据源**：复用 K 线数据，前端计算
```javascript
// 计算阶段涨幅
const periodReturns = {
    '5d': (close[-1] / close[-6] - 1) * 100,
    '20d': (close[-1] / close[-21] - 1) * 100,
    '60d': (close[-1] / close[-61] - 1) * 100,
    'ytd': (close[-1] / close[yearStart] - 1) * 100,
};
```

**UI**：在行情数据区增加"阶段涨幅"卡片，红涨绿跌

#### 1.3 内外盘 + 涨跌停价
**数据源**：扩展 `/api/stock/detail/{code}` 接口
```python
# quote_service.py 新增字段
@dataclass(frozen=True)
class QuoteData:
    # ... 现有字段 ...
    outer_volume: float = 0.0  # 外盘
    inner_volume: float = 0.0  # 内盘
    limit_up: float = 0.0      # 涨停价
    limit_down: float = 0.0    # 跌停价
```

**东方财富 API 字段**：
- 外盘: `f47` 的一部分（需要单独接口）
- 涨停价/跌停价: 计算公式 `昨收 * (1 ± 10%)`（主板）或 `昨收 * (1 ± 20%)`（创业板/科创板）

---

### 第2期：基本面分析增强

#### 2.1 利润趋势图
**数据源**：新增 API `/api/stock/profit-trend/{code}`
```python
# 东方财富财务数据接口
# type=RPT_F10_FINANCE_MAINFINADATA 已有，需要取多期数据
@router.get("/profit-trend/{code}")
async def get_profit_trend(code: str):
    # 取最近8个季度的营收和净利润
    url = f"https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "REPORT_DATE,TOTALOPERATEREVE,PARENTNETPROFIT",
        "filter": f'(SECURITY_CODE="{code}")',
        "p": 1, "ps": 8, "sr": -1, "st": "REPORT_DATE"
    }
    # 返回 [{date, revenue, net_profit}, ...]
```

**UI**：Chart.js 折线图，双Y轴（营收左轴，净利润右轴）

#### 2.2 股东研究
**数据源**：新增 API `/api/stock/shareholders/{code}`
```python
# 东方财富股东数据接口
# type=RPT_F10_EH_HOLDERSNUM（股东人数）
# type=RPT_F10_EH_FREEHOLDERS（十大流通股东）
```

**UI**：表格展示十大流通股东 + 股东人数变化趋势图

#### 2.3 分红历史
**数据源**：新增 API `/api/stock/dividends/{code}`
```python
# 东方财富分红接口
# type=RPT_F10_FHPS_DET 或从 F10 页面抓取
```

**UI**：表格展示历次分红送转记录

#### 2.4 公告信息
**数据源**：新增 API `/api/stock/announcements/{code}`
```python
# 东方财富公告接口
url = f"https://np-anotice-stock.eastmoney.com/api/security/ann"
params = {
    "sr": -1, "page_size": 20, "page_index": 1,
    "ann_type": "A", "stock_list": code,
    "f_node": 0, "s_node": 0
}
```

**UI**：列表展示最近20条公告，点击跳转原文

---

### 第3期：高级分析功能

#### 3.1 行业对比
**数据源**：新增 API `/api/stock/industry-comparison/{code}`
```python
# 获取同行业股票列表 + 基本面数据
# 1. 从 detail 接口获取 industry 字段
# 2. 搜索同行业股票
# 3. 批量获取 PE/PB/ROE 数据
```

**UI**：表格 + 散点图（PE vs ROE）

#### 3.2 北向资金
**数据源**：新增 API `/api/stock/northbound/{code}`
```python
# 东方财富沪深港通接口
url = f"https://datacenter.eastmoney.com/securities/api/data/get"
params = {
    "type": "RPT_MUTUAL_STOCK_NORTHSTA",
    "filter": f'(SECURITY_CODE="{code}")',
}
```

**UI**：折线图展示北向持仓变化

#### 3.3 筹码分布
**数据源**：需要逐日成交量分布数据，计算复杂
**UI**：横向柱状图，显示各价位的持仓成本分布

#### 3.4 龙虎榜 / 融资融券
**数据源**：东方财富数据中心 API
**UI**：表格展示

---

## 技术架构

### 前端架构
```
dashboard/static/
├── stock-detail.js          # 主入口，模块编排
├── stock-charts.js          # 图表模块（K线、分时、技术指标）
├── stock-fundamentals.js    # 基本面模块（财务、股东、分红）
├── stock-capital-flow.js    # 资金流向模块
├── stock-orderbook.js       # 五档盘口模块
├── technical-indicators.js  # 技术指标计算引擎
└── stock-detail.css         # 样式
```

### 后端架构
```
dashboard/routers/
├── stock_detail.py          # 现有（行情、K线、盘口、资金流向）
├── stock_fundamentals.py    # 新增（财务趋势、股东、分红）
├── stock_market.py          # 新增（行业对比、北向资金）
└── stock_news.py            # 新增（公告、新闻、研报）
```

### 数据源汇总
| 数据 | API来源 | 缓存策略 |
|------|---------|----------|
| 实时行情 | push2.eastmoney.com | 5秒轮询 |
| K线数据 | push2his.eastmoney.com | 本地缓存 |
| 财务数据 | datacenter.eastmoney.com | 1小时缓存 |
| 股东数据 | datacenter.eastmoney.com | 1天缓存 |
| 公告数据 | np-anotice-stock.eastmoney.com | 30分钟缓存 |
| 北向资金 | datacenter.eastmoney.com | 1天缓存 |

---

## 实施优先级

### P0 - 必须（第1期，1-2天）
1. ✅ 技术指标引擎（MACD/KDJ/RSI/BOLL/WR/OBV）
2. ✅ K线图副图区域
3. ✅ 阶段涨幅卡片
4. ✅ 内外盘数据
5. ✅ 涨跌停价

### P1 - 重要（第2期，2-3天）
1. 利润趋势图
2. 股东研究
3. 分红历史
4. 公告信息

### P2 - 增强（第3期，3-5天）
1. 行业对比
2. 北向资金
3. 筹码分布
4. 龙虎榜/融资融券

---

## 页面布局设计

```
┌─────────────────────────────────────────────────────────────┐
│  股票代码/名称搜索                                             │
├─────────────────────────────────────────────────────────────┤
│  价格 ¥11.37  涨跌 +0.01 (+0.09%)  成交量 93.7万手           │
│  今开 11.37  昨收 11.36  最高 11.39  最低 11.30              │
│  涨停 12.50  跌停 10.22  换手率 0.09%  量比 0.53             │
│  外盘 45.2万  内盘 48.5万                                    │
├──────────────────────┬──────────────────────────────────────┤
│  阶段涨幅            │  专业指标                              │
│  5日: +2.3%         │  52周高: ¥13.09                       │
│  20日: -1.5%        │  52周低: ¥10.29                       │
│  60日: +5.8%        │  均量5日: 126.9万                      │
│  年初至今: +8.2%     │  均量10日: 126.2万                     │
├──────────────────────┴──────────────────────────────────────┤
│  [分时] [日K] [周K] [月K] [60分] [15分] [5分]  指标▼ [MACD] │
├───────────────────────────────────────┬─────────────────────┤
│                                       │  五档盘口           │
│         K线图 / 分时图                 │  卖5 11.42  1200    │
│         + 技术指标副图                 │  卖4 11.41  800     │
│                                       │  卖3 11.40  1500    │
│                                       │  卖2 11.39  2000    │
│                                       │  卖1 11.38  500     │
│                                       │  买1 11.37  800     │
│                                       │  买2 11.36  1200    │
│                                       │  买3 11.35  600     │
│                                       │  买4 11.34  1000    │
│                                       │  买5 11.33  500     │
├───────────────────────────────────────┴─────────────────────┤
│  资金流向（近20日）                                           │
│  [柱状图: 主力净流入 + 超大单]                                │
├─────────────────────────────────────────────────────────────┤
│  [财务指标] [股东研究] [分红历史] [公告] [行业对比]            │
├─────────────────────────────────────────────────────────────┤
│  利润趋势图（近8季度）                                        │
│  [双Y轴折线图: 营收 + 净利润]                                │
├─────────────────────────────────────────────────────────────┤
│  行业对比                                                    │
│  [表格: 同行业PE/PB/ROE对比]                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 依赖和风险

### 外部依赖
- LightweightCharts v4（K线图）— 已有
- Chart.js v4（柱状图/折线图）— 已有
- 东方财富公开 API — 免费，有频率限制

### 风险
1. **API 频率限制**：需要加缓存层，避免频繁请求
2. **数据一致性**：不同 API 接口的数据更新时间可能不同步
3. **前端性能**：技术指标计算量较大，需要优化（Web Worker）
4. **移动端适配**：图表在小屏幕上需要响应式设计

### 缓存策略
```python
# 使用 functools.lru_cache 或 Redis 缓存
from functools import lru_cache

@lru_cache(maxsize=1000)
def _fetch_financial_data(code: str) -> dict:
    # 缓存1小时
    pass
```

---

## 验收标准

### 第1期验收
- [ ] K线图支持 MACD/KDJ/RSI/BOLL 四个技术指标切换
- [ ] 技术指标计算正确（与东方财富对比误差<0.1%）
- [ ] 阶段涨幅数据正确
- [ ] 内外盘数据正确
- [ ] 涨跌停价计算正确

### 第2期验收
- [ ] 利润趋势图显示近8季度数据
- [ ] 股东研究显示十大流通股东
- [ ] 分红历史表格完整
- [ ] 公告列表可点击查看原文

### 第3期验收
- [ ] 行业对比表格数据正确
- [ ] 北向资金趋势图可用
- [ ] 筹码分布图可用
