# AI Alpha 页面全面升级方案

> 目标：打造行业顶级的 AI Alpha 因子研究与策略评估平台

## 现状分析

### 已实现（4 个图表）
- 因子重要性 Top20（水平条形图）
- 模型训练曲线（AUC + Loss 双轴）
- 预测 vs 实际（概率折线图）
- K 线 + 买卖信号

### 已实现但未暴露
- XGBoost 模型（`alpha/models/xgb_model.py`）
- Ensemble 集成模型（`alpha/models/ensemble_model.py`）
- Optuna 超参优化（`alpha/optimizer.py`）
- 策略评估器 Sharpe/Sortino/Calmar/胜率（`alpha/evaluator.py`）

### 核心缺陷
1. 每次请求重新训练模型，无缓存
2. 只有买入信号，无卖出信号
3. 无因子评价体系（IC/IR/分层/换手率）
4. 无过拟合检测
5. 无可解释性（SHAP）
6. 无多模型对比
7. 无 Walk-forward 验证
8. 无策略绩效面板

---

## 实现阶段（10 个 Phase，按优先级排序）

---

### Phase 1：暴露已有模块 + 卖出信号 + 模型缓存

**目标**：把写好的代码用起来，解决最大架构问题

#### 1.1 模型缓存（`dashboard/routers/alpha.py`）

```python
# 新增模型缓存层
import hashlib
from pathlib import Path

MODEL_CACHE_DIR = Path("models/alpha_cache")
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _cache_key(code: str, start: str, end: str, model_type: str) -> str:
    raw = f"{code}_{start}_{end}_{model_type}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_or_train(code, start, end, model_type="lightgbm", force_retrain=False):
    """带缓存的模型训练"""
    key = _cache_key(code, start, end, model_type)
    cache_path = MODEL_CACHE_DIR / f"{key}.txt"

    if not force_retrain and cache_path.exists():
        model = _create_model(model_type)
        model.load(str(cache_path))
        return model

    model = _train_model_impl(code, start, end, model_type)
    model.save(str(cache_path))
    return model
```

#### 1.2 多模型选择器（`dashboard/routers/alpha.py`）

```python
# 所有端点增加 model_type 参数
@router.post("/predict")
async def predict_signals(req: PredictRequest):
    # req.model_type: "lightgbm" | "xgboost" | "ensemble"
    model = _get_or_train(req.code, req.start_date, req.end_date, req.model_type)
    ...
```

#### 1.3 卖出信号生成

```python
# 当前只有 signal=1(买) 和 signal=0(无操作)
# 改为双阈值：
def predict_signal(X, buy_threshold=0.6, sell_threshold=0.4):
    probs = model.predict(X)
    signals = pd.Series(0, index=X.index)  # 0=持有
    signals[probs > buy_threshold] = 1      # 1=买入
    signals[probs < sell_threshold] = -1    # -1=卖出
    return signals
```

#### 1.4 前端模型选择器（`index.html` + `alpha.js`）

```html
<!-- 在日期选择器旁增加 -->
<select id="alpha-model" aria-label="选择模型">
    <option value="lightgbm">LightGBM</option>
    <option value="xgboost">XGBoost</option>
    <option value="ensemble">集成模型</option>
</select>
<button onclick="App.optimizeAlpha()">超参优化</button>
<button onclick="App.loadAlpha({forceRetrain: true})">重新训练</button>
```

#### 1.5 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/routers/alpha.py` | 模型缓存 + 多模型 + 卖出信号 + 优化端点 |
| 改 | `dashboard/static/alpha.js` | 模型选择器 + 卖出信号渲染 + 优化按钮 |
| 改 | `dashboard/templates/index.html` | 增加模型选择下拉框 + 优化按钮 |

---

### Phase 2：策略绩效仪表盘

**目标**：把 evaluator.py 的指标展示出来

#### 2.1 新增 API 端点

```python
@router.post("/performance")
async def get_performance(req: PerformanceRequest):
    """基于模型信号的策略绩效评估"""
    model = _get_or_train(req.code, req.start_date, req.end_date, req.model_type)
    # 用模型信号模拟交易 → 构建权益曲线 → 调用 evaluator
    equity_curve = _simulate_equity(df, signals, initial_cash=1_000_000)
    metrics = StrategyEvaluator.evaluate(equity_curve)
    trade_metrics = StrategyEvaluator.evaluate_trades(trades)
    return {**metrics, **trade_metrics, "equity_curve": equity_curve}
```

#### 2.2 前端绩效面板

```html
<!-- 新增绩效统计卡片 -->
<div class="stats-grid stats-grid-6" id="alpha-perf-stats">
    <div class="stat-card"><div class="stat-label">总收益率</div><div class="stat-value" id="alpha-total-return">--</div></div>
    <div class="stat-card"><div class="stat-label">年化收益</div><div class="stat-value" id="alpha-annual-return">--</div></div>
    <div class="stat-card"><div class="stat-label">最大回撤</div><div class="stat-value" id="alpha-max-dd">--</div></div>
    <div class="stat-card"><div class="stat-label">夏普比率</div><div class="stat-value" id="alpha-sharpe">--</div></div>
    <div class="stat-card"><div class="stat-label">胜率</div><div class="stat-value" id="alpha-win-rate">--</div></div>
    <div class="stat-card"><div class="stat-label">盈亏比</div><div class="stat-value" id="alpha-profit-ratio">--</div></div>
</div>

<!-- 权益曲线图 -->
<div class="card">
    <h2>策略权益曲线</h2>
    <div class="chart-container chart-h-lg"><canvas id="alpha-equity-chart"></canvas></div>
</div>
```

#### 2.3 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/routers/alpha.py` | 新增 `/performance` 端点 |
| 改 | `dashboard/static/alpha.js` | 新增 `renderPerformance()` + 权益曲线 |
| 改 | `dashboard/templates/index.html` | 绩效卡片 + 权益曲线 canvas |

---

### Phase 3：因子评价体系（IC/IR/分层/换手率）

**目标**：回答"这个因子到底有没有预测力"

#### 3.1 因子评价引擎（`alpha/factor_evaluator.py`）

```python
class FactorEvaluator:
    """因子评价：IC/IR/分层收益/换手率"""

    @staticmethod
    def calc_ic(factor: pd.Series, forward_returns: pd.Series) -> float:
        """信息系数：因子与未来收益的 Spearman 相关"""
        return factor.corr(forward_returns, method='spearman')

    @staticmethod
    def calc_ic_series(factor_df: pd.DataFrame, returns_df: pd.DataFrame, period: int = 1) -> pd.Series:
        """滚动 IC 序列"""
        fwd_ret = returns_df.shift(-period)
        return factor_df.corrwith(fwd_ret, method='spearman')

    @staticmethod
    def calc_ir(ic_series: pd.Series) -> float:
        """信息比率：IC 均值 / IC 标准差"""
        return ic_series.mean() / ic_series.std() if ic_series.std() > 0 else 0

    @staticmethod
    def quantile_returns(factor: pd.Series, returns: pd.Series, n_quantiles: int = 5) -> pd.DataFrame:
        """分层回测：按因子值分 N 组，计算各组平均收益"""
        groups = pd.qcut(factor, n_quantiles, labels=False, duplicates='drop')
        result = returns.groupby(groups).agg(['mean', 'std', 'count'])
        result.columns = ['mean_return', 'std', 'count']
        return result

    @staticmethod
    def calc_turnover(factor: pd.Series, top_pct: float = 0.2) -> float:
        """因子换手率：Top 组合每日成分变化比例"""
        n = int(len(factor) * top_pct)
        today_top = set(factor.nlargest(n).index)
        yesterday_top = set(factor.shift(1).nlargest(n).index)
        if not yesterday_top:
            return 0.0
        changed = len(today_top - yesterday_top)
        return changed / len(today_top)
```

#### 3.2 API 端点

```python
@router.post("/factor-eval")
async def evaluate_factors(req: FactorEvalRequest):
    """单因子评价：IC/IR/分层/换手率"""
    df = storage.get_stock_daily(req.code, req.start, req.end)
    features = pipeline.build_features(df)
    fwd_returns = df["close"].pct_change(req.forward_period).shift(-req.forward_period)

    results = []
    for col in features.columns:
        if col in ("date", "label"):
            continue
        ic_series = FactorEvaluator.calc_ic_series(features[col], fwd_returns)
        results.append({
            "factor": col,
            "ic_mean": round(ic_series.mean(), 4),
            "ic_std": round(ic_series.std(), 4),
            "ir": round(FactorEvaluator.calc_ir(ic_series), 4),
            "turnover": round(FactorEvaluator.calc_turnover(features[col]), 4),
        })
    return sorted(results, key=lambda x: abs(x["ir"]), reverse=True)
```

#### 3.3 前端因子评价面板

- **IC 时序图**：各因子的滚动 IC 折线
- **分层收益柱状图**：5 组分层的平均收益
- **因子评价表**：factor / IC均值 / IR / 换手率，按 |IR| 排序
- **IC 热力图**：所有因子的 IC 值矩阵

#### 3.4 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 新 | `alpha/factor_evaluator.py` | IC/IR/分层/换手率计算 |
| 改 | `dashboard/routers/alpha.py` | 新增 `/factor-eval` 端点 |
| 改 | `dashboard/static/alpha.js` | 新增 `renderFactorEval()` |
| 改 | `dashboard/templates/index.html` | 因子评价面板 UI |

---

### Phase 4：SHAP 可解释性

**目标**：从"哪个因子重要"升级到"为什么重要 + 如何影响"

#### 4.1 SHAP 计算（`alpha/explainer.py`）

```python
import shap

class ModelExplainer:
    """SHAP 模型解释器"""

    @staticmethod
    def calc_shap_values(model, X: pd.DataFrame) -> np.ndarray:
        """计算 SHAP 值"""
        explainer = shap.TreeExplainer(model._model)
        return explainer.shap_values(X)

    @staticmethod
    def global_importance(shap_values: np.ndarray, feature_names: list) -> pd.DataFrame:
        """全局特征重要性（SHAP 版本）"""
        importance = np.abs(shap_values).mean(axis=0)
        return pd.DataFrame({
            "feature": feature_names,
            "shap_importance": importance
        }).sort_values("shap_importance", ascending=False)

    @staticmethod
    def dependence_data(shap_values, X, feature_name) -> dict:
        """SHAP 依赖图数据：特征值 vs SHAP 值"""
        idx = list(X.columns).index(feature_name)
        return {
            "feature_values": X.iloc[:, idx].tolist(),
            "shap_values": shap_values[:, idx].tolist(),
        }
```

#### 4.2 API 端点

```python
@router.post("/shap")
async def get_shap(req: ShapRequest):
    """SHAP 可解释性分析"""
    model = _get_or_train(req.code, req.start, req.end, req.model_type)
    X, y = _get_features(req.code, req.start, req.end)

    shap_values = ModelExplainer.calc_shap_values(model, X)

    # 全局重要性
    global_imp = ModelExplainer.global_importance(shap_values, list(X.columns))

    # SHAP 依赖图（Top 3 因子）
    top_features = global_imp.head(3)["feature"].tolist()
    dependence = {}
    for feat in top_features:
        dependence[feat] = ModelExplainer.dependence_data(shap_values, X, feat)

    return {
        "global_importance": global_imp.to_dict("records"),
        "dependence": dependence,
        "sample_shap_values": shap_values[:100].tolist(),  # 前 100 条用于 beeswarm
    }
```

#### 4.3 前端 SHAP 面板

- **SHAP Beeswarm 图**（替代当前的 feature importance 条形图）
- **SHAP 依赖图**：散点图，X 轴 = 特征值，Y 轴 = SHAP 值
- **单样本解释**：选择某一天，展示各因子的贡献方向和大小

#### 4.4 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 新 | `alpha/explainer.py` | SHAP 计算逻辑 |
| 改 | `dashboard/routers/alpha.py` | 新增 `/shap` 端点 |
| 改 | `dashboard/static/alpha.js` | SHAP beeswarm + 依赖图 |
| 改 | `dashboard/templates/index.html` | SHAP 面板 UI |

---

### Phase 5：过拟合检测 + Walk-forward 验证

**目标**：让用户知道模型是否可信

#### 5.1 Walk-forward 引擎（`alpha/walk_forward.py`）

```python
class WalkForwardValidator:
    """滚动窗口验证"""

    def __init__(self, train_days: int = 252, test_days: int = 21, step_days: int = 21):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

    def validate(self, X: pd.DataFrame, y: pd.Series, model_factory) -> list[dict]:
        """滚动验证，返回每个窗口的指标"""
        results = []
        n = len(X)
        start = 0

        while start + self.train_days + self.test_days <= n:
            train_end = start + self.train_days
            test_end = min(train_end + self.test_days, n)

            X_train, y_train = X.iloc[start:train_end], y.iloc[start:train_end]
            X_test, y_test = X.iloc[train_end:test_end], y.iloc[train_end:test_end]

            model = model_factory()
            model.train(X_train, y_train)

            test_pred = model.predict(X_test)
            auc = roc_auc_score(y_test, test_pred) if len(y_test.unique()) > 1 else 0.5

            results.append({
                "window_start": str(X.index[start]),
                "window_end": str(X.index[test_end - 1]),
                "train_auc": 0,  # 需要单独计算
                "test_auc": round(auc, 4),
                "n_train": len(X_train),
                "n_test": len(X_test),
            })
            start += self.step_days

        return results
```

#### 5.2 过拟合检测器

```python
class OverfitDetector:
    """过拟合检测"""

    @staticmethod
    def detect(train_auc: float, val_auc: float, threshold: float = 0.1) -> dict:
        gap = train_auc - val_auc
        return {
            "train_auc": round(train_auc, 4),
            "val_auc": round(val_auc, 4),
            "gap": round(gap, 4),
            "gap_pct": round(gap / max(train_auc, 0.01) * 100, 2),
            "is_overfit": gap > threshold,
            "severity": "danger" if gap > 0.15 else "warning" if gap > 0.1 else "ok",
        }

    @staticmethod
    def walk_forward_stability(wf_results: list[dict]) -> dict:
        """Walk-forward 稳定性分析"""
        aucs = [r["test_auc"] for r in wf_results]
        return {
            "mean_auc": round(np.mean(aucs), 4),
            "std_auc": round(np.std(aucs), 4),
            "min_auc": round(min(aucs), 4),
            "max_auc": round(max(aucs), 4),
            "is_stable": np.std(aucs) < 0.05,
            "trend": "declining" if len(aucs) > 2 and aucs[-1] < aucs[0] else "stable",
        }
```

#### 5.3 API 端点

```python
@router.post("/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    """Walk-forward 滚动验证"""
    ...

@router.post("/overfit-check")
async def overfit_check(req: OverfitRequest):
    """过拟合检测"""
    ...
```

#### 5.4 前端

- **Walk-forward AUC 折线图**：每个窗口的 test AUC，带均值线
- **过拟合警告卡片**：train/val gap 超阈值时显示红色警告
- **稳定性指标**：AUC 均值/标准差/趋势

#### 5.5 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 新 | `alpha/walk_forward.py` | Walk-forward 验证引擎 |
| 新 | `alpha/overfit_detector.py` | 过拟合检测器 |
| 改 | `dashboard/routers/alpha.py` | 新增 2 个端点 |
| 改 | `dashboard/static/alpha.js` | WF 图 + 过拟合警告 |
| 改 | `dashboard/templates/index.html` | WF 面板 + 警告 UI |

---

### Phase 6：多模型对比

**目标**：并排对比 LightGBM / XGBoost / Ensemble 的表现

#### 6.1 API 端点

```python
@router.post("/compare")
async def compare_models(req: CompareRequest):
    """多模型对比"""
    results = {}
    for model_type in ["lightgbm", "xgboost", "ensemble"]:
        model = _get_or_train(req.code, req.start, req.end, model_type)
        # 计算各模型的 AUC、准确率、Sharpe 等
        results[model_type] = {
            "auc": ...,
            "accuracy": ...,
            "sharpe": ...,
            "feature_importance": model.feature_importance().head(10).to_dict("records"),
        }
    return results
```

#### 6.2 前端

- **对比表格**：3 个模型的关键指标并排
- **对比柱状图**：AUC/Sharpe/胜率 对比
- **特征重要性对比**：3 个模型的 Top10 因子并排

#### 6.3 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/routers/alpha.py` | 新增 `/compare` 端点 |
| 改 | `dashboard/static/alpha.js` | 对比图表 |
| 改 | `dashboard/templates/index.html` | 对比面板 |

---

### Phase 7：因子相关性分析

**目标**：发现冗余因子，辅助降维

#### 7.1 API 端点

```python
@router.post("/factor-correlation")
async def factor_correlation(req: FactorCorrelationReq):
    """因子相关性矩阵"""
    df = storage.get_stock_daily(req.code, req.start, req.end)
    features = pipeline.build_features(df)
    feature_cols = [c for c in features.columns if c not in ("date", "label")]
    corr_matrix = features[feature_cols].corr(method='spearman')
    return {
        "factors": feature_cols,
        "matrix": corr_matrix.round(3).values.tolist(),
        "high_corr_pairs": _find_high_corr(corr_matrix, threshold=0.8),
    }
```

#### 7.2 前端

- **热力图**：因子相关性矩阵（用 canvas 或 heatmap.js 渲染）
- **高相关因子警告**：|corr| > 0.8 的因子对高亮

#### 7.3 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/routers/alpha.py` | 新增 `/factor-correlation` |
| 改 | `dashboard/static/alpha.js` | 热力图渲染 |
| 改 | `dashboard/templates/index.html` | 热力图 canvas |

---

### Phase 8：因子衰减分析

**目标**：看因子预测力随持仓天数的变化

#### 8.1 API 端点

```python
@router.post("/factor-decay")
async def factor_decay(req: FactorDecayRequest):
    """因子预测力衰减分析"""
    # 对每个因子，计算 1/5/10/20/60 日 forward 的 IC
    periods = [1, 5, 10, 20, 60]
    results = {}
    for factor_name in top_factors:
        results[factor_name] = {}
        for p in periods:
            fwd_ret = df["close"].pct_change(p).shift(-p)
            ic = features[factor_name].corr(fwd_ret, method='spearman')
            results[factor_name][f"{p}d"] = round(ic, 4)
    return results
```

#### 8.2 前端

- **衰减曲线**：X 轴 = 持仓天数，Y 轴 = IC，每条线一个因子
- 找出哪些因子是"短期有效"vs"长期有效"

#### 8.3 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/routers/alpha.py` | 新增 `/factor-decay` |
| 改 | `dashboard/static/alpha.js` | 衰减曲线图 |
| 改 | `dashboard/templates/index.html` | 衰减面板 |

---

### Phase 9：自动因子挖掘

**目标**：自动组合发现新 Alpha

#### 9.1 因子挖掘器（`alpha/factor_miner.py`）

```python
class AlphaMiner:
    """自动因子挖掘：组合/变换/筛选"""

    OPERATIONS = {
        "diff": lambda a, b: a - b,
        "ratio": lambda a, b: a / b.replace(0, np.nan),
        "product": lambda a, b: a * b,
        "zscore_cross": lambda a, b: (a - a.rolling(20).mean()) / a.rolling(20).std() * b,
    }

    def mine(self, features: pd.DataFrame, top_n: int = 20) -> list[dict]:
        """尝试所有两两组合，按 IC 筛选"""
        candidates = []
        factor_cols = [c for c in features.columns if c not in ("date", "label")]

        for i, a in enumerate(factor_cols):
            for b in factor_cols[i+1:]:
                for op_name, op_fn in self.OPERATIONS.items():
                    new_factor = op_fn(features[a], features[b])
                    ic = new_factor.corr(features["label"], method='spearman')
                    if abs(ic) > 0.03:  # 最低阈值
                        candidates.append({
                            "name": f"{op_name}({a},{b})",
                            "ic": round(ic, 4),
                            "abs_ic": round(abs(ic), 4),
                        })

        return sorted(candidates, key=lambda x: x["abs_ic"], reverse=True)[:top_n]
```

#### 9.2 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 新 | `alpha/factor_miner.py` | 自动因子挖掘 |
| 改 | `dashboard/routers/alpha.py` | 新增 `/mine` 端点 |
| 改 | `dashboard/static/alpha.js` | 挖掘结果表 |
| 改 | `dashboard/templates/index.html` | 挖掘面板 |

---

### Phase 10：页面重构 — Tab 化布局

**目标**：当前 4 个图表平铺太拥挤，改为子 Tab 结构

#### 10.1 新布局

```
AI Alpha 页面
├── 顶部：股票选择 + 日期 + 模型选择 + 操作按钮
├── 绩效概览卡片（6 个 stat-card）
├── 子 Tab 导航
│   ├── [模型分析] 训练曲线 + 预测 vs 实际 + 过拟合警告
│   ├── [因子研究] 因子重要性 + SHAP + 因子评价表 + 相关性热力图 + 衰减曲线
│   ├── [交易信号] K 线 + 买卖信号 + 权益曲线
│   ├── [模型对比] 多模型并排对比
│   ├── [Walk-forward] 滚动验证 AUC 曲线 + 稳定性指标
│   └── [因子挖掘] 自动挖掘结果 + 新因子列表
└── 底部：超参优化面板（折叠式）
```

#### 10.2 文件清单

| 操作 | 文件 | 改动 |
|------|------|------|
| 改 | `dashboard/templates/index.html` | 子 Tab 结构重构 |
| 改 | `dashboard/static/alpha.js` | 子 Tab 切换逻辑 |
| 改 | `dashboard/static/app.js` | initAlpha 适配 |

---

## 依赖安装

```bash
# 新增 Python 依赖
pip install shap

# 已有依赖（确认版本）
pip install lightgbm xgboost optuna scikit-learn pandas numpy
```

---

## 实施顺序与工作量估算

| Phase | 内容 | 工作量 | 优先级 |
|-------|------|--------|--------|
| 1 | 模型缓存 + 多模型 + 卖出信号 | 中 | P0 |
| 2 | 策略绩效仪表盘 | 中 | P0 |
| 3 | 因子评价体系 IC/IR | 大 | P0 |
| 4 | SHAP 可解释性 | 中 | P1 |
| 5 | 过拟合检测 + Walk-forward | 大 | P1 |
| 6 | 多模型对比 | 小 | P1 |
| 7 | 因子相关性热力图 | 小 | P2 |
| 8 | 因子衰减分析 | 小 | P2 |
| 9 | 自动因子挖掘 | 中 | P2 |
| 10 | 页面 Tab 重构 | 大 | 最后做 |

**建议实施路径**：Phase 1 → 2 → 3 → 10 → 4 → 5 → 6 → 7 → 8 → 9

理由：先打通数据流和核心功能（1-3），然后重构页面布局（10），再逐步添加高级功能（4-9）。

---

## 完成后的功能矩阵

| 类别 | 功能 | 行业对标 |
|------|------|---------|
| **模型** | LightGBM / XGBoost / Ensemble 三选一 | Qlib |
| **模型** | Optuna 超参优化 | 标配 |
| **模型** | 模型缓存/持久化 | 标配 |
| **模型** | 多模型对比 | 标配 |
| **因子** | 因子重要性（gain） | 标配 |
| **因子** | SHAP 可解释性 | 2025 趋势 |
| **因子** | IC/IR/分层/换手率 | Alphalens |
| **因子** | 因子相关性热力图 | 标配 |
| **因子** | 因子衰减分析 | 进阶 |
| **因子** | 自动因子挖掘 | Qlib AutoAlpha |
| **验证** | 过拟合检测 | 专业级 |
| **验证** | Walk-forward 滚动验证 | 专业级 |
| **策略** | 权益曲线 + Sharpe/Sortino/Calmar | 标配 |
| **策略** | 胜率/盈亏比/盈利因子 | 标配 |
| **信号** | 买入 + 卖出双信号 | 基本功能 |
| **信号** | K 线信号叠加 | 标配 |
