"""Provider-agnostic AI analysis runtime.

The runtime owns AI tasks, provider diagnostics, agent opinions, and report
artifacts.  It deliberately has no dependency on the deterministic decision
runtime: AI output is explanatory research only.
"""

from .context import build_analysis_context
from .models import (
    AIReport,
    AnalysisContext,
    GenerationError,
    GenerationErrorCode,
    ProviderChannel,
    TaskStatus,
)
from .runtime import AIRuntime

__all__ = [
    "AIReport",
    "AIRuntime",
    "AnalysisContext",
    "GenerationError",
    "GenerationErrorCode",
    "ProviderChannel",
    "TaskStatus",
    "build_analysis_context",
]
