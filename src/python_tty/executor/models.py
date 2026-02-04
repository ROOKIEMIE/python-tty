from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class Invocation:
    run_id: Optional[str] = None
    source: str = "tty"
    origin_source: Optional[str] = None
    principal: Optional[str] = None
    console_id: Optional[str] = None
    command_id: Optional[str] = None
    command_name: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    lock_key: str = "global"
    timeout_ms: Optional[int] = None
    audit_policy: Optional[str] = None
    session_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    depth: int = 0
    callable_meta: Optional[Dict[str, Any]] = None
    meta_revision: Optional[str] = None
    raw_cmd: Optional[str] = None


@dataclass
class RunState:
    run_id: str
    source: Optional[str] = None
    origin_source: Optional[str] = None
    principal: Optional[str] = None
    session_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    depth: int = 0
    command_id: Optional[str] = None
    callable_meta: Optional[Dict[str, Any]] = None
    lock_key: Optional[str] = None
    status: RunStatus = RunStatus.PENDING
    result: Any = None
    error: Optional[BaseException] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
