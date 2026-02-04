from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Literal

from python_tty.session.policy import SessionPolicy


@dataclass
class SessionState:
    session_id: str
    principal: str
    created_at: float
    last_activity_at: float
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    policy: SessionPolicy
    tags: Dict[str, Any] = field(default_factory=dict)
    run_ids: Deque[str] = field(default_factory=deque)
