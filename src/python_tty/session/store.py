import threading
import time
from typing import Any, Dict, List, Optional

from python_tty.session.models import SessionState


class SessionStore:
    """In-memory session state store."""
    def __init__(self, retain_last_n: Optional[int] = 100):
        self._retain_last_n = retain_last_n
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def create(self, state: SessionState) -> SessionState:
        with self._lock:
            if state.session_id in self._sessions:
                raise ValueError(f"Session already exists: {state.session_id}")
            self._sessions[state.session_id] = state
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self, filters: Optional[Dict[str, Any]] = None) -> List[SessionState]:
        filters = filters or {}
        status_filter = _normalize_filter(filters.get("status"))
        principal_filter = _normalize_filter(filters.get("principal"))
        with self._lock:
            sessions = list(self._sessions.values())
        results: List[SessionState] = []
        for state in sessions:
            if status_filter and state.status not in status_filter:
                continue
            if principal_filter and state.principal not in principal_filter:
                continue
            results.append(state)
        return results

    def close(self, session_id: str, status: str = "CLOSED") -> Optional[SessionState]:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            state.status = status
            state.last_activity_at = time.time()
            return state

    def touch(self, session_id: str, ts: Optional[float] = None) -> Optional[SessionState]:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            state.last_activity_at = time.time() if ts is None else float(ts)
            return state

    def add_run(self, session_id: str, run_id: str) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return
            state.run_ids.append(run_id)

    def remove(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def gc(self, now: Optional[float] = None) -> List[str]:
        now = time.time() if now is None else float(now)
        expired: List[str] = []
        with self._lock:
            sessions = list(self._sessions.values())
        for state in sessions:
            ttl = state.policy.idle_ttl_seconds
            if ttl is None:
                continue
            if state.status != "OPEN":
                continue
            if now - state.last_activity_at >= ttl:
                expired.append(state.session_id)
        if not expired:
            return []
        with self._lock:
            for session_id in expired:
                state = self._sessions.get(session_id)
                if state is None:
                    continue
                state.status = "EXPIRED"
        return expired

    def retain_last_n(self) -> Optional[int]:
        return self._retain_last_n


def _normalize_filter(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value}
