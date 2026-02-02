import asyncio
import time
from typing import Dict, List, Optional


class RunEventBus:
    def __init__(self, max_events: Optional[int] = None, ttl_seconds: Optional[float] = None):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[object]] = {}
        self._max_events = max_events
        self._ttl_seconds = ttl_seconds

    def publish(self, run_id: Optional[str], event: object):
        if run_id is None:
            return
        self._history.setdefault(run_id, []).append(event)
        self._prune_history(run_id)
        for queue in list(self._subscribers.get(run_id, [])):
            queue.put_nowait(event)

    def subscribe(self, run_id: str, since_seq: int = 0) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        if since_seq is not None and since_seq >= 0:
            for event in self._history.get(run_id, []):
                seq = getattr(event, "seq", 0) or 0
                if seq > since_seq:
                    queue.put_nowait(event)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        try:
            subscribers.remove(queue)
        except ValueError:
            return
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def drop(self, run_id: str):
        self._subscribers.pop(run_id, None)
        self._history.pop(run_id, None)

    def _prune_history(self, run_id: str):
        history = self._history.get(run_id)
        if not history:
            return
        if self._ttl_seconds is not None:
            cutoff = time.time() - self._ttl_seconds
            while history:
                ts = getattr(history[0], "ts", None)
                if ts is None or ts >= cutoff:
                    break
                history.pop(0)
        if self._max_events is not None and self._max_events >= 0:
            if len(history) > self._max_events:
                del history[:-self._max_events]
