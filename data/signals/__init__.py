"""Unified signal engine package.

The legacy Qlib-compatible cache is treated as one signal provider. Consumers
should depend on this package instead of reading Qlib cache details directly.
"""

from data.signals.engine import (
    DEFAULT_PROVIDER,
    build_signal_context,
    get_signal_records,
)

__all__ = ["DEFAULT_PROVIDER", "build_signal_context", "get_signal_records"]
