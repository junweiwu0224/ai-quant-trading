"""动态策略加载器：从 Python 代码实例化自定义策略"""
import ast
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from strategy.base import BaseStrategy

# 安全的内置函数白名单 — 阻止 __import__、__subclasses__ 等危险访问
_BLOCKED_BUILTINS = frozenset({
    'os', 'sys', 'subprocess', 'shutil', 'importlib', 'eval', 'exec', 'compile',
    'open', 'input', 'globals', 'locals', 'breakpoint', 'exit', 'quit',
    '__import__', '__build_class__', '__loader__',
})

# 允许的导入模块白名单
_ALLOWED_IMPORT_ROOTS = frozenset({
    'strategy', 'numpy', 'math', 'statistics', 'collections', 'itertools',
    'datetime', 'typing', 'dataclasses', 'enum', 'abc', 'copy', 'functools',
})


def _build_safe_builtins() -> dict:
    """构建受限的 builtins 字典（移除危险内置函数）"""
    source = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    return {k: v for k, v in source.items() if k not in _BLOCKED_BUILTINS}


class _StrategyCodeValidator(ast.NodeVisitor):
    """AST 白名单验证器 — 阻止危险的导入和 dunder 属性访问"""

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split('.')[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                raise ValueError(f"禁止导入: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            root = node.module.split('.')[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                raise ValueError(f"禁止导入: {node.module}")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        attr = node.attr
        # 阻止 __dunder__ 属性访问（__class__, __bases__, __subclasses__ 等）
        if attr.startswith('__') and attr.endswith('__'):
            if attr not in ('__init__', '__name__', '__dict__', '__doc__'):
                raise ValueError(f"禁止访问 dunder 属性: {attr}")
        self.generic_visit(node)


def _validate_code_ast(code: str):
    """AST 级别安全检查，失败抛出 ValueError"""
    tree = ast.parse(code, '<strategy>')
    _StrategyCodeValidator().visit(tree)


def load_strategy_from_code(
    code: str,
    class_name: str = "CustomStrategy",
    params: Optional[dict] = None,
) -> Optional[BaseStrategy]:
    """从 Python 源代码动态加载策略类并实例化

    Args:
        code: Python 源代码，必须定义一个继承 BaseStrategy 的类
        class_name: 策略类名，默认 CustomStrategy
        params: 传递给策略构造函数的参数

    Returns:
        策略实例，失败返回 None
    """
    try:
        # AST 白名单验证（在 exec 之前拦截危险代码）
        _validate_code_ast(code)

        # 创建临时模块
        module_name = f"_custom_strategy_{id(code)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        if spec is None:
            logger.error("无法创建模块 spec")
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        # 注入受限 builtins + 预导入安全模块
        exec_globals = {
            "__builtins__": _build_safe_builtins(),
            "__name__": module_name,
        }
        exec("from strategy.base import BaseStrategy, Bar, Order, Trade, Portfolio", exec_globals)
        exec("import numpy as np", exec_globals)

        # 执行代码
        exec(code, exec_globals)

        # 查找策略类
        strategy_cls = None
        for name, obj in exec_globals.items():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseStrategy)
                and obj is not BaseStrategy
            ):
                strategy_cls = obj
                break

        if strategy_cls is None:
            logger.error(f"代码中未找到继承 BaseStrategy 的类 (期望类名: {class_name})")
            return None

        # 实例化
        instance = strategy_cls(**(params or {}))
        logger.info(f"动态加载策略成功: {strategy_cls.__name__}")
        return instance

    except SyntaxError as e:
        logger.error(f"策略代码语法错误: {e}")
        return None
    except Exception as e:
        logger.error(f"加载策略失败: {e}")
        return None
    finally:
        # 清理临时模块
        if module_name in sys.modules:
            del sys.modules[module_name]


def validate_strategy_code(code: str) -> tuple[bool, str]:
    """验证策略代码是否合法

    Returns:
        (is_valid, error_message)
    """
    try:
        # AST 白名单验证（不执行代码，只做语法和安全检查）
        _validate_code_ast(code)
    except SyntaxError as e:
        return False, f"语法错误: 行 {e.lineno}: {e.msg}"
    except ValueError as e:
        return False, f"安全检查失败: {e}"

    # AST 检查是否有 BaseStrategy 子类
    try:
        tree = ast.parse(code, '<strategy>')
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name == "BaseStrategy":
                        found = True
                        break
        if not found:
            return False, "代码中未找到继承 BaseStrategy 的策略类"
    except Exception as e:
        return False, f"解析错误: {e}"

    return True, ""


# 策略代码模板
STRATEGY_TEMPLATE = '''"""自定义策略模板"""
from strategy.base import BaseStrategy, Bar


class CustomStrategy(BaseStrategy):
    """在此编写你的策略逻辑"""

    def __init__(self, short_window: int = 5, long_window: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.short_window = short_window
        self.long_window = long_window
        self._prices = []
        self._holding = False

    def on_bar(self, bar: Bar):
        """每个 K 线触发"""
        self._prices.append(bar.close)

        # 保持窗口大小
        if len(self._prices) < self.long_window:
            return

        # 计算均线
        short_ma = sum(self._prices[-self.short_window:]) / self.short_window
        long_ma = sum(self._prices[-self.long_window:]) / self.long_window

        # 交易逻辑
        if not self._holding and short_ma > long_ma:
            self.buy(bar.code, 100)
            self._holding = True
        elif self._holding and short_ma < long_ma:
            self.sell(bar.code, 100)
            self._holding = False
'''
