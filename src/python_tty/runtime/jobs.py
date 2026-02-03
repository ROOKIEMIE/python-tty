import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from python_tty.executor.models import Invocation, RunState, RunStatus
from python_tty.runtime.event_bus import RunEventBus


class JobStore:
    def __init__(self,
                 retain_last_n: Optional[int] = None,
                 ttl_seconds: Optional[float] = None,
                 event_history_max: Optional[int] = None,
                 event_history_ttl: Optional[float] = None):
        self._runs: Dict[str, RunState] = {}
        self._invocations: Dict[str, Invocation] = {}
        self._run_futures: Dict[str, asyncio.Future] = {}
        self._event_seq: Dict[str, int] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._event_bus = RunEventBus(
            max_events=event_history_max,
            ttl_seconds=event_history_ttl,
        )
        self._retain_last_n = retain_last_n
        self._ttl_seconds = ttl_seconds
        self._loop = None
        self._global_subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()

    @property
    def runs(self):
        return self._runs

    def set_loop(self, loop):
        self._loop = loop

    def create_run(self, invocation: Invocation) -> RunState:
        run_id = invocation.run_id
        if run_id is None:
            raise ValueError("Invocation run_id is required for JobStore")
        run_state = RunState(run_id=run_id)
        with self._lock:
            self._runs[run_id] = run_state
            self._invocations[run_id] = invocation
            self._cancel_flags[run_id] = threading.Event()
        return run_state

    def set_future(self, run_id: str, future: asyncio.Future):
        with self._lock:
            self._run_futures[run_id] = future

    def get_future(self, run_id: str):
        with self._lock:
            return self._run_futures.get(run_id)

    def get_run_state(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            return self._runs.get(run_id)

    def get_invocation(self, run_id: str) -> Optional[Invocation]:
        with self._lock:
            return self._invocations.get(run_id)

    def get(self, run_id: str):
        with self._lock:
            return {
                "run_state": self._runs.get(run_id),
                "invocation": self._invocations.get(run_id),
            }

    def list(self, filters: Optional[Dict[str, Any]] = None):
        filters = filters or {}
        status_filter = _normalize_filter(filters.get("status"))
        source_filter = _normalize_filter(filters.get("source"))
        principal_filter = _normalize_filter(filters.get("principal"))
        command_filter = _normalize_filter(filters.get("command_id"))
        results = []
        with self._lock:
            runs = list(self._runs.items())
            invocations = dict(self._invocations)
        for run_id, run_state in runs:
            invocation = invocations.get(run_id)
            if status_filter and run_state.status not in status_filter:
                continue
            if source_filter and invocation is not None and invocation.source not in source_filter:
                continue
            if principal_filter and invocation is not None and invocation.principal not in principal_filter:
                continue
            if command_filter and invocation is not None and invocation.command_id not in command_filter:
                continue
            results.append({
                "run_id": run_id,
                "status": run_state.status,
                "source": getattr(invocation, "source", None),
                "principal": getattr(invocation, "principal", None),
                "command_id": getattr(invocation, "command_id", None),
                "started_at": run_state.started_at,
                "finished_at": run_state.finished_at,
            })
        return results

    async def result(self, run_id: str):
        future = self.get_future(run_id)
        if future is None:
            run_state = self.get_run_state(run_id)
            if run_state is None:
                return None
            if run_state.error is not None:
                raise run_state.error
            return run_state.result
        return await future

    def resolve_future(self, run_id: str, result=None, error: Optional[BaseException] = None):
        future = self.get_future(run_id)
        if future is None or future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def next_event_seq(self, run_id: str) -> int:
        with self._lock:
            next_seq = self._event_seq.get(run_id, 0) + 1
            self._event_seq[run_id] = next_seq
        return next_seq

    def publish_event(self, run_id: str, event: object):
        self._event_bus.publish(run_id, event)
        with self._lock:
            subscribers = list(self._global_subscribers)
        for queue in subscribers:
            queue.put_nowait(event)

    def events(self, run_id: str, since_seq: int = 0) -> asyncio.Queue:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and (self._loop is None or running_loop == self._loop):
            return self._event_bus.subscribe(run_id, since_seq)
        if running_loop is not None and self._loop is not None and running_loop != self._loop:
            raise RuntimeError("events must be called from the executor loop")
        raise RuntimeError("events requires a running event loop")

    def unsubscribe_events(self, run_id: str, queue: asyncio.Queue):
        self._event_bus.unsubscribe(run_id, queue)

    def subscribe_all(self) -> asyncio.Queue:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and (self._loop is None or running_loop == self._loop):
            queue: asyncio.Queue = asyncio.Queue()
            with self._lock:
                self._global_subscribers.append(queue)
            return queue
        if running_loop is not None and self._loop is not None and running_loop != self._loop:
            raise RuntimeError("subscribe_all must be called from the executor loop")
        raise RuntimeError("subscribe_all requires a running event loop")

    def unsubscribe_all(self, queue: asyncio.Queue):
        with self._lock:
            try:
                self._global_subscribers.remove(queue)
            except ValueError:
                return

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            flag = self._cancel_flags.get(run_id)
            if flag is None:
                return False
            return flag.is_set()

    def get_cancel_flag(self, run_id: str):
        with self._lock:
            return self._cancel_flags.get(run_id)

    def cancel(self, run_id: str) -> str:
        with self._lock:
            run_state = self._runs.get(run_id)
            if run_state is None:
                return "missing"
            flag = self._cancel_flags.get(run_id)
            if flag is not None:
                flag.set()
            if run_state.status == RunStatus.PENDING:
                run_state.status = RunStatus.CANCELLED
                run_state.finished_at = time.time()
                run_state.error = asyncio.CancelledError()
                future = self._run_futures.get(run_id)
                if future is not None and not future.done():
                    future.set_exception(run_state.error)
                return "cancelled"
            if run_state.status == RunStatus.RUNNING:
                return "requested"
            return "noop"

    def pop_run(self, run_id: str):
        with self._lock:
            run_state = self._runs.pop(run_id, None)
            future = self._run_futures.pop(run_id, None)
            self._event_seq.pop(run_id, None)
            self._invocations.pop(run_id, None)
            self._cancel_flags.pop(run_id, None)
        if future is not None and not future.done():
            future.cancel()
        self._event_bus.drop(run_id)
        return run_state

    def cleanup(self):
        if self._retain_last_n is None and self._ttl_seconds is None:
            return
        now = time.time()
        completed = []
        with self._lock:
            runs = list(self._runs.items())
        for run_id, run_state in runs:
            if run_state.status in (RunStatus.PENDING, RunStatus.RUNNING):
                continue
            completed.append((run_state.finished_at, run_id))
        remove_ids = set()
        if self._ttl_seconds is not None:
            for finished_at, run_id in completed:
                if finished_at is None:
                    continue
                if now - finished_at >= self._ttl_seconds:
                    remove_ids.add(run_id)
        if self._retain_last_n is not None and self._retain_last_n >= 0:
            completed.sort(reverse=True)
            for _, run_id in completed[self._retain_last_n:]:
                remove_ids.add(run_id)
        for run_id in remove_ids:
            self.pop_run(run_id)


def _normalize_filter(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value}
