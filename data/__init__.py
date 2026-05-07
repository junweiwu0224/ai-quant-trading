# 延迟导入，避免未安装 akshare 时无法使用 storage
def __getattr__(name):
    if name == "StockCollector":
        from data.collector import StockCollector
        return StockCollector
    elif name == "DataStorage":
        from data.storage import DataStorage
        return DataStorage
    elif name == "DataScheduler":
        from data.scheduler import DataScheduler
        return DataScheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
