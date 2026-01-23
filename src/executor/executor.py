import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.config import ExecutorConfig
from src.ui.events import UIEvent, UIEventLevel
from src.ui.output import get_output_router
from src.executor.models import Invocation, RunState, RunStatus


@dataclass
class WorkItem:
    invocation: Invocation
    handler: Callable[[Invocation], object]


class CommandExecutor:
    def __init__(self, workers: int = 1, loop=None, config: ExecutorConfig = None):
        if config is None:
            config = ExecutorConfig(workers=workers)
        self._config = config
        self._worker_count = config.workers
        self._loop = loop
        self._queue = None
        self._workers = []
        self._locks: Dict[str, asyncio.Lock] = {}
        self._runs: Dict[str, RunState] = {}
        self._event_queues: Dict[str, asyncio.Queue] = {}
        self._run_futures: Dict[str, asyncio.Future] = {}
        self._retain_last_n = config.retain_last_n
        self._ttl_seconds = config.ttl_seconds
        self._pop_on_wait = config.pop_on_wait
        self._output_router = get_output_router()

    @property
    def runs(self):
        return self._runs

    def start(self, loop=None):
        if loop is not None:
            self._loop = loop
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError("Executor start requires a running event loop") from exc
        if self._queue is None:
            self._queue = asyncio.Queue()
        if self._workers:
            return
        for _ in range(self._worker_count):
            self._workers.append(self._loop.create_task(self._worker_loop()))

    def submit(self, invocation: Invocation, handler: Optional[Callable[[Invocation], object]] = None) -> str:
        if invocation.run_id is None:
            invocation.run_id = str(uuid.uuid4())
        if handler is None:
            handler = self._missing_handler
        run_id = invocation.run_id
        self._runs[run_id] = RunState(run_id=run_id)
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        if self._loop is None or not self._loop.is_running():
            self._run_inline(invocation, handler)
            return run_id
        self.start()
        self._run_futures[run_id] = self._loop.create_future()
        self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))
        return run_id

    async def wait_result(self, run_id: str):
        try:
            future = self._run_futures.get(run_id)
            if future is None:
                run_state = self._runs.get(run_id)
                if run_state is None:
                    return None
                if run_state.error is not None:
                    raise run_state.error
                return run_state.result
            return await future
        finally:
            if self._pop_on_wait:
                self.pop_run(run_id)

    def wait_result_sync(self, run_id: str, timeout: Optional[float] = None):
        try:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is not None and running_loop == self._loop:
                raise RuntimeError("wait_result_sync cannot be called from the executor loop thread")
            future = self._run_futures.get(run_id)
            if future is not None and self._loop is not None and self._loop.is_running():
                result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
                return result_future.result(timeout)
            run_state = self._runs.get(run_id)
            if run_state is None:
                return None
            if run_state.status in (RunStatus.PENDING, RunStatus.RUNNING):
                if self._loop is not None and self._loop.is_running():
                    result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
                    return result_future.result(timeout)
                raise RuntimeError("Run is still pending but executor loop is not running")
            if run_state.error is not None:
                raise run_state.error
            return run_state.result
        finally:
            if self._pop_on_wait:
                self.pop_run(run_id)

    def stream_events(self, run_id: str):
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        return self._event_queues.setdefault(run_id, asyncio.Queue())

    def publish_event(self, run_id: str, event):
        if getattr(event, "run_id", None) is None:
            event.run_id = run_id
        if self._loop is not None and self._loop.is_running():
            queue = self._event_queues.setdefault(run_id, asyncio.Queue())
            queue.put_nowait(event)
        if self._output_router is not None:
            self._output_router.emit(event)

    async def shutdown(self, wait: bool = True):
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        if wait and workers:
            await asyncio.gather(*workers, return_exceptions=True)

    def shutdown_threadsafe(self, wait: bool = True, timeout: Optional[float] = None):
        loop = self._loop
        if loop is None or not loop.is_running():
            for task in list(self._workers):
                task.cancel()
            self._workers.clear()
            return None
        future = asyncio.run_coroutine_threadsafe(self.shutdown(wait=wait), loop)
        return future.result(timeout)

    def submit_threadsafe(self, invocation: Invocation,
                          handler: Optional[Callable[[Invocation], object]] = None) -> str:
        if invocation.run_id is None:
            invocation.run_id = str(uuid.uuid4())
        if handler is None:
            handler = self._missing_handler
        run_id = invocation.run_id
        self._runs[run_id] = RunState(run_id=run_id)
        if self._loop is None or not self._loop.is_running():
            return self.submit(invocation, handler=handler)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self.submit(invocation, handler=handler)

        async def _enqueue():
            self.start()
            self._run_futures[run_id] = self._loop.create_future()
            self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))

        asyncio.run_coroutine_threadsafe(_enqueue(), self._loop).result()
        return run_id

    async def _worker_loop(self):
        while True:
            work_item = await self._queue.get()
            run_state = self._runs.get(work_item.invocation.run_id)
            lock = self._locks.setdefault(work_item.invocation.lock_key, asyncio.Lock())
            async with lock:
                await self._execute_work_item(work_item, run_state)
            self._queue.task_done()

    async def _execute_work_item(self, work_item: WorkItem, run_state: Optional[RunState]):
        if run_state is None:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self.publish_event(run_state.run_id, self._build_run_event("start", UIEventLevel.INFO))
        try:
            result = work_item.handler(work_item.invocation)
            if inspect.isawaitable(result):
                result = await result
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self.publish_event(run_state.run_id, self._build_run_event("success", UIEventLevel.SUCCESS))
            self._resolve_future(run_state, result=result)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self.publish_event(
                run_state.run_id,
                self._build_run_event("failure", UIEventLevel.ERROR, payload={"error": str(exc)}),
            )
            self._resolve_future(run_state, error=exc)
        finally:
            run_state.finished_at = time.time()
            self._cleanup_runs()

    def _resolve_future(self, run_state: RunState, result=None, error: Optional[BaseException] = None):
        future = self._run_futures.get(run_state.run_id)
        if future is None or future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def _run_inline(self, invocation: Invocation, handler):
        run_state = self._runs.get(invocation.run_id)
        if run_state is None:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self.publish_event(run_state.run_id, self._build_run_event("start", UIEventLevel.INFO))
        try:
            result = handler(invocation)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self.publish_event(run_state.run_id, self._build_run_event("success", UIEventLevel.SUCCESS))
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self.publish_event(
                run_state.run_id,
                self._build_run_event("failure", UIEventLevel.ERROR, payload={"error": str(exc)}),
            )
        finally:
            run_state.finished_at = time.time()
            self._cleanup_runs()

    @staticmethod
    def _build_run_event(event_type: str, level: UIEventLevel, payload=None):
        return UIEvent(msg=event_type, level=level, event_type=event_type, payload=payload)

    @staticmethod
    def _missing_handler(invocation: Invocation):
        raise RuntimeError("No handler provided for invocation execution")

    def pop_run(self, run_id: str):
        run_state = self._runs.pop(run_id, None)
        future = self._run_futures.pop(run_id, None)
        if future is not None and not future.done():
            future.cancel()
        self._event_queues.pop(run_id, None)
        return run_state

    def _cleanup_runs(self):
        if self._retain_last_n is None and self._ttl_seconds is None:
            return
        now = time.time()
        completed = []
        for run_id, run_state in self._runs.items():
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
