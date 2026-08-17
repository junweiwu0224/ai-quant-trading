"""Small immutable records used by the decision storage adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StoredRecord:
    id: str
    workspace_id: str
    payload: dict[str, Any]

