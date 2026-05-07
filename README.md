# AI Quant Trading

基于 vnpy 深度定制的 A股量化交易系统。

## 系统架构

```
数据采集 → 因子研究 → 策略回测 → 模拟交易 → 实盘交易 → AI 自学习优化
```

## 模块

| 模块 | 说明 |
|------|------|
| data/ | 数据采集与存储（AKShare） |
| strategy/ | 策略模板与内置策略 |
| alpha/ | AI 因子挖掘与模型训练 |
| risk/ | 风控规则引擎 |
| dashboard/ | Web 可视化面板 |
| engine/ | vnpy 引擎集成（回测/模拟/实盘） |

## 技术栈

- Python 3.10+
- vnpy 4.3
- AKShare
- FastAPI
- LightGBM + Optuna
- SQLite / MySQL

## 开发阶段

1. **Phase 1** — 基础搭建（数据层）
2. **Phase 2** — 回测引擎
3. **Phase 3** — AI Alpha
4. **Phase 4** — 风控模块
5. **Phase 5** — 模拟盘
6. **Phase 6** — 可视化面板
7. **Phase 7** — 实盘对接

详见 [架构设计文档](docs/ARCHITECTURE.md)

## License

MIT
