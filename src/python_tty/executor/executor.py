import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from python_tty.config import ExecutorConfig
from python_tty.runtime.context import use_run_context
from python_tty.runtime.event_bus import RunEventBus
from python_tty.runtime.events import RuntimeEvent, RuntimeEventKind, UIEventLevel
from python_tty.runtime.provider import get_router
from python_tty.executor.models import Invocation, RunState, RunStatus
from python_tty.exceptions.console_exception import ConsoleExit, SubConsoleExit


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
        self._event_bus = RunEventBus(
            max_events=config.event_history_max,
            ttl_seconds=config.event_history_ttl,
        )
        self._event_seq: Dict[str, int] = {}
        self._run_futures: Dict[str, asyncio.Future] = {}
        self._retain_last_n = config.retain_last_n
        self._ttl_seconds = config.ttl_seconds
        self._pop_on_wait = config.pop_on_wait
        self._emit_run_events = config.emit_run_events
        if config.exempt_exceptions is None:
            self._exempt_exceptions = (ConsoleExit, SubConsoleExit)
        else:
            self._exempt_exceptions = tuple(config.exempt_exceptions)
        self._audit_sink = self._init_audit_sink(config)

    @property
    def runs(self):
        return self._runs

    @property
    def audit_sink(self):
        return self._audit_sink

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
        self._audit_invocation(invocation)
        self._audit_run_state(self._runs[run_id])
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

    def stream_events(self, run_id: str, since_seq: int = 0):
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        return self._ensure_event_subscription(run_id, since_seq)

    def publish_event(self, run_id: str, event):
        if getattr(event, "run_id", None) is None:
            event.run_id = run_id
        if run_id is not None and getattr(event, "seq", None) is None:
            event.seq = self._next_event_seq(run_id)
        if self._loop is not None and self._loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop == self._loop:
                self._event_bus.publish(run_id, event)
            else:
                self._loop.call_soon_threadsafe(self._event_bus.publish, run_id, event)
        else:
            self._event_bus.publish(run_id, event)
        output_router = get_router()
        if output_router is not None:
            output_router.emit(event)
        if self._audit_sink is not None:
            output_audit = None
            if output_router is not None:
                output_audit = getattr(output_router, "audit_sink", None)
            if output_audit is None or output_audit is not self._audit_sink:
                self._audit_sink.record_event(event)

    async def shutdown(self, wait: bool = True):
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        if wait and workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._close_audit_sink()

    def shutdown_threadsafe(self, wait: bool = True, timeout: Optional[float] = None):
        loop = self._loop
        if loop is None or not loop.is_running():
            for task in list(self._workers):
                task.cancel()
            self._workers.clear()
            self._close_audit_sink()
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
        self._audit_invocation(invocation)
        self._audit_run_state(self._runs[run_id])

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
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=work_item.invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            with use_run_context(run_id=run_state.run_id,
                                 source=work_item.invocation.source,
                                 emitter=emitter):
                result = work_item.handler(work_item.invocation)
                if inspect.isawaitable(result):
                    result = await result
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=work_item.invocation.source)
            self._resolve_future(run_state, result=result)
        except self._exempt_exceptions as exc:
            run_state.error = exc
            run_state.status = RunStatus.CANCELLED
            self._emit_run_event(run_state.run_id, "cancelled", UIEventLevel.INFO,
                                 source=work_item.invocation.source)
            self._resolve_future(run_state, error=exc)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self._emit_run_event(
                run_state.run_id,
                "failure",
                UIEventLevel.ERROR,
                payload={"error": str(exc)},
                source=work_item.invocation.source,
                force=True,
            )
            self._resolve_future(run_state, error=exc)
        finally:
            run_state.finished_at = time.time()
            self._audit_run_state(run_state)
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
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            with use_run_context(run_id=run_state.run_id,
                                 source=invocation.source,
                                 emitter=emitter):
                result = handler(invocation)
                if inspect.isawaitable(result):
                    result = self._run_awaitable_inline(result)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=invocation.source)
        except self._exempt_exceptions as exc:
            run_state.error = exc
            run_state.status = RunStatus.CANCELLED
            self._emit_run_event(run_state.run_id, "cancelled", UIEventLevel.INFO,
                                 source=invocation.source)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self._emit_run_event(
                run_state.run_id,
                "failure",
                UIEventLevel.ERROR,
                payload={"error": str(exc)},
                source=invocation.source,
                force=True,
            )
        finally:
            run_state.finished_at = time.time()
            self._audit_run_state(run_state)
            self._cleanup_runs()

    @staticmethod
    def _build_run_event(event_type: str, level: UIEventLevel, payload=None, source=None):
        return RuntimeEvent(
            kind=RuntimeEventKind.STATE,
            msg=event_type,
            level=level,
            event_type=event_type,
            payload=payload,
            source=source,
        )

    def _emit_run_event(self, run_id: str, event_type: str, level: UIEventLevel,
                        payload=None, source=None, force: bool = False):
        if force or self._emit_run_events:
            self.publish_event(run_id, self._build_run_event(event_type, level, payload=payload, source=source))

    @staticmethod
    def _missing_handler(invocation: Invocation):
        raise RuntimeError("No handler provided for invocation execution")

    def _ensure_event_subscription(self, run_id: str, since_seq: int = 0):
        if self._loop is None or not self._loop.is_running():
            return self._event_bus.subscribe(run_id, since_seq)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self._event_bus.subscribe(run_id, since_seq)
        future = asyncio.run_coroutine_threadsafe(
            self._create_event_subscription(run_id, since_seq),
            self._loop,
        )
        return future.result()

    async def _create_event_subscription(self, run_id: str, since_seq: int = 0):
        return self._event_bus.subscribe(run_id, since_seq)

    def _init_audit_sink(self, config: ExecutorConfig):
        audit_config = getattr(config, "audit", None)
        if audit_config is None or not audit_config.enabled:
            return None
        if audit_config.sink is not None:
            return audit_config.sink
        from python_tty.audit import AuditSink
        return AuditSink(
            file_path=audit_config.file_path,
            stream=audit_config.stream,
            keep_in_memory=audit_config.keep_in_memory,
            async_mode=audit_config.async_mode,
            flush_interval=audit_config.flush_interval,
        )

    def _audit_invocation(self, invocation: Invocation):
        if self._audit_sink is None:
            return
        self._audit_sink.record_invocation(invocation)

    def _audit_run_state(self, run_state: RunState):
        if self._audit_sink is None:
            return
        self._audit_sink.record_run_state(run_state)

    def _close_audit_sink(self):
        if self._audit_sink is None:
            return
        self._audit_sink.close()

    def _next_event_seq(self, run_id: str) -> int:
        next_seq = self._event_seq.get(run_id, 0) + 1
        self._event_seq[run_id] = next_seq
        return next_seq

    def _run_awaitable_inline(self, awaitable):
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if asyncio.isfuture(awaitable):
            raise RuntimeError("Inline awaitable must be a coroutine, not a Future/Task")
        if running_loop is None:
            return asyncio.run(self._awaitable_to_coroutine(awaitable))
        if self._loop is not None and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._awaitable_to_coroutine(awaitable),
                self._loop,
            )
            return future.result()
        raise RuntimeError("Cannot run awaitable inline while an event loop is running")

    @staticmethod
    def _awaitable_to_coroutine(awaitable):
        if asyncio.iscoroutine(awaitable):
            return awaitable

        async def _await_obj():
            return await awaitable

        return _await_obj()

    def pop_run(self, run_id: str):
        run_state = self._runs.pop(run_id, None)
        future = self._run_futures.pop(run_id, None)
        if future is not None and not future.done():
            future.cancel()
        self._event_seq.pop(run_id, None)
        self._event_bus.drop(run_id)
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

