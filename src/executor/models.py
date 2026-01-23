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
    principal: Optional[str] = None
    console_id: Optional[str] = None
    command_id: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    lock_key: str = "global"
    timeout_ms: Optional[int] = None
    audit_policy: Optional[str] = None
    raw_cmd: Optional[str] = None


@dataclass
class RunState:
    run_id: str
    status: RunStatus = RunStatus.PENDING
    result: Any = None
    error: Optional[BaseException] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
