from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class SessionPolicy:
    """Session-level execution policy."""
    default_lock_key_mode: Literal["session", "global", "none"] = "session"
    max_concurrent_runs: int = 8
    default_timeout_ms: Optional[int] = None
    idle_ttl_seconds: Optional[float] = 3600.0
