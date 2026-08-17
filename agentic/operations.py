"""Value objects for auditable, idempotent domain commands."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


class OperationConflict(RuntimeError):
    """An operation id was reused for different command facts."""


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    command: str
    aggregate_type: str
    aggregate_id: str
    request: Mapping[str, Any]
    request_hash: str
    status: str
    result: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        if not str(self.operation_id).strip():
            raise ValueError("operation_id is required")
        if not str(self.command).strip():
            raise ValueError("operation command is required")
        if self.status not in {"completed", "rejected", "recovery_required"}:
            raise ValueError("unsupported operation status: %s" % self.status)
        object.__setattr__(self, "request", dict(self.request or {}))
        object.__setattr__(self, "result", dict(self.result or {}))


def normalize_operation_id(operation_id: str | None) -> str:
    value = str(operation_id or "").strip()
    if not value:
        raise ValueError("operation_id is required")
    if len(value) > 128:
        raise ValueError("operation_id must be at most 128 characters")
    return value


def operation_request_hash(request: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(request or {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
