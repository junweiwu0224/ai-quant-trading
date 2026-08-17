"""Engine package exports with lazy loading for optional runtime dependencies."""

__all__ = ["BacktestEngine", "BacktestConfig", "BacktestResult"]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    from engine.backtest_engine import BacktestConfig, BacktestEngine, BacktestResult

    values = {
        "BacktestEngine": BacktestEngine,
        "BacktestConfig": BacktestConfig,
        "BacktestResult": BacktestResult,
    }
    return values[name]
