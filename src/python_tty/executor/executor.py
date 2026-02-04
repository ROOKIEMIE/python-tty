import asyncio
import functools
import inspect
import time
import uuid
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

from python_tty.config import ExecutorConfig
from python_tty.runtime.context import use_run_context
from python_tty.runtime.events import RuntimeEvent, RuntimeEventKind, UIEventLevel
from python_tty.runtime.jobs import JobStore
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
        self._job_store = JobStore(
            retain_last_n=config.retain_last_n,
            ttl_seconds=config.ttl_seconds,
            event_history_max=config.event_history_max,
            event_history_ttl=config.event_history_ttl,
        )
        self._pop_on_wait = config.pop_on_wait
        self._emit_run_events = config.emit_run_events
        self._sync_in_threadpool = config.sync_in_threadpool
        self._threadpool = None
        if self._sync_in_threadpool:
            self._threadpool = ThreadPoolExecutor(max_workers=config.threadpool_workers)
        if config.exempt_exceptions is None:
            self._exempt_exceptions = (ConsoleExit, SubConsoleExit, asyncio.CancelledError)
        else:
            self._exempt_exceptions = tuple(config.exempt_exceptions)
        self._audit_sink = self._init_audit_sink(config)

    @property
    def runs(self):
        return self._job_store.runs

    @property
    def job_store(self):
        return self._job_store

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
        self._job_store.set_loop(self._loop)
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
        run_state = self._job_store.create_run(invocation)
        self._audit_invocation(invocation)
        self._audit_run_state(run_state)
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        if self._loop is None or not self._loop.is_running():
            self._run_inline(invocation, handler)
            return run_id
        self.start()
        self._job_store.set_future(run_id, self._loop.create_future())
        self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))
        return run_id

    async def wait_result(self, run_id: str):
        try:
            return await self._job_store.result(run_id)
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
            future = self._job_store.get_future(run_id)
            if future is not None and self._loop is not None and self._loop.is_running():
                result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
                return result_future.result(timeout)
            run_state = self._job_store.get_run_state(run_id)
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

    def cancel(self, run_id: str) -> str:
        status = self._job_store.cancel(run_id)
        if status == "cancelled":
            invocation = self._job_store.get_invocation(run_id)
            source = getattr(invocation, "source", None)
            run_state = self._job_store.get_run_state(run_id)
            if run_state is not None:
                self._audit_run_state(run_state)
            self._emit_run_event(run_id, "cancelled", UIEventLevel.INFO, source=source, force=True)
        elif status == "requested":
            invocation = self._job_store.get_invocation(run_id)
            source = getattr(invocation, "source", None)
            self._emit_run_event(run_id, "cancel_requested", UIEventLevel.INFO, source=source, force=True)
        return status

    def stream_events(self, run_id: str, since_seq: int = 0, maxsize: int = 0):
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        return self._ensure_event_subscription(run_id, since_seq, maxsize)

    def publish_event(self, run_id: str, event):
        if getattr(event, "run_id", None) is None:
            event.run_id = run_id
        if run_id is not None and getattr(event, "seq", None) is None:
            event.seq = self._job_store.next_event_seq(run_id)
        if self._loop is not None and self._loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop == self._loop:
                self._job_store.publish_event(run_id, event)
            else:
                self._loop.call_soon_threadsafe(self._job_store.publish_event, run_id, event)
        else:
            self._job_store.publish_event(run_id, event)
        if self._audit_sink is not None:
            self._audit_sink.record_event(event)

    async def shutdown(self, wait: bool = True):
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        if wait and workers:
            await asyncio.gather(*workers, return_exceptions=True)
        if self._threadpool is not None:
            self._threadpool.shutdown(wait=wait)
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
        if self._loop is None or not self._loop.is_running():
            return self.submit(invocation, handler=handler)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self.submit(invocation, handler=handler)
        run_state = self._job_store.create_run(invocation)
        self._audit_invocation(invocation)
        self._audit_run_state(run_state)

        async def _enqueue():
            self.start()
            self._job_store.set_future(run_id, self._loop.create_future())
            self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))

        asyncio.run_coroutine_threadsafe(_enqueue(), self._loop).result()
        return run_id

    async def _worker_loop(self):
        while True:
            work_item = await self._queue.get()
            run_state = self._job_store.get_run_state(work_item.invocation.run_id)
            lock_key = getattr(work_item.invocation, "lock_key", None)
            if not lock_key:
                await self._execute_work_item(work_item, run_state)
            else:
                lock = self._locks.setdefault(lock_key, asyncio.Lock())
                async with lock:
                    await self._execute_work_item(work_item, run_state)
            self._queue.task_done()

    async def _execute_work_item(self, work_item: WorkItem, run_state: Optional[RunState]):
        if run_state is None:
            return
        if run_state.status == RunStatus.CANCELLED:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=work_item.invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            cancel_flag = self._job_store.get_cancel_flag(run_state.run_id)
            with use_run_context(run_id=run_state.run_id,
                                 source=work_item.invocation.source,
                                 emitter=emitter,
                                 cancel_flag=cancel_flag,
                                 session_id=getattr(work_item.invocation, "session_id", None),
                                 parent_run_id=getattr(work_item.invocation, "parent_run_id", None),
                                 depth=getattr(work_item.invocation, "depth", None),
                                 origin_source=getattr(work_item.invocation, "origin_source", None),
                                 principal=getattr(work_item.invocation, "principal", None),
                                 lock_key=getattr(work_item.invocation, "lock_key", None),
                                 command_id=getattr(work_item.invocation, "command_id", None),
                                 callable_meta=getattr(work_item.invocation, "callable_meta", None)):
                timeout = self._timeout_seconds(work_item.invocation)
                result = await self._run_handler(work_item.invocation, work_item.handler, timeout)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=work_item.invocation.source)
            self._resolve_future(run_state, result=result)
        except asyncio.TimeoutError as exc:
            run_state.error = exc
            run_state.status = RunStatus.TIMEOUT
            self._emit_run_event(run_state.run_id, "timeout", UIEventLevel.WARNING,
                                 source=work_item.invocation.source, force=True)
            self._resolve_future(run_state, error=exc)
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
            self._job_store.cleanup()

    def _resolve_future(self, run_state: RunState, result=None, error: Optional[BaseException] = None):
        self._job_store.resolve_future(run_state.run_id, result=result, error=error)

    def _run_inline(self, invocation: Invocation, handler):
        run_state = self._job_store.get_run_state(invocation.run_id)
        if run_state is None:
            return
        if run_state.status == RunStatus.CANCELLED:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            cancel_flag = self._job_store.get_cancel_flag(run_state.run_id)
            with use_run_context(run_id=run_state.run_id,
                                 source=invocation.source,
                                 emitter=emitter,
                                 cancel_flag=cancel_flag,
                                 session_id=getattr(invocation, "session_id", None),
                                 parent_run_id=getattr(invocation, "parent_run_id", None),
                                 depth=getattr(invocation, "depth", None),
                                 origin_source=getattr(invocation, "origin_source", None),
                                 principal=getattr(invocation, "principal", None),
                                 lock_key=getattr(invocation, "lock_key", None),
                                 command_id=getattr(invocation, "command_id", None),
                                 callable_meta=getattr(invocation, "callable_meta", None)):
                timeout = self._timeout_seconds(invocation)
                result = self._run_handler_inline(invocation, handler, timeout)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=invocation.source)
        except asyncio.TimeoutError as exc:
            run_state.error = exc
            run_state.status = RunStatus.TIMEOUT
            self._emit_run_event(run_state.run_id, "timeout", UIEventLevel.WARNING,
                                 source=invocation.source, force=True)
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
            self._job_store.cleanup()

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
            event = self._build_run_event(event_type, level, payload=payload, source=source)
            self._attach_event_context(event, run_id)
            self.publish_event(run_id, event)

    @staticmethod
    def _missing_handler(invocation: Invocation):
        raise RuntimeError("No handler provided for invocation execution")

    @staticmethod
    def _timeout_seconds(invocation: Invocation) -> Optional[float]:
        timeout_ms = getattr(invocation, "timeout_ms", None)
        if timeout_ms is None:
            return None
        return max(0.0, timeout_ms / 1000.0)

    async def _run_handler(self, invocation: Invocation, handler, timeout: Optional[float]):
        start = time.monotonic()
        if inspect.iscoroutinefunction(handler):
            result = handler(invocation)
            if timeout is None:
                return await result
            return await asyncio.wait_for(result, timeout)
        if self._sync_in_threadpool and self._threadpool is not None:
            loop = asyncio.get_running_loop()
            func = functools.partial(handler, invocation)
            task = loop.run_in_executor(self._threadpool, func)
            if timeout is None:
                result = await task
            else:
                result = await asyncio.wait_for(task, timeout)
            if inspect.isawaitable(result):
                if timeout is None:
                    return await result
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                return await asyncio.wait_for(result, remaining)
            return result
        result = handler(invocation)
        if inspect.isawaitable(result):
            if timeout is None:
                return await result
            return await asyncio.wait_for(result, timeout)
        if timeout is not None:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError()
        return result

    def _run_handler_inline(self, invocation: Invocation, handler, timeout: Optional[float]):
        start = time.monotonic()
        result = handler(invocation)
        if inspect.isawaitable(result):
            if timeout is None:
                return self._run_awaitable_inline(result)
            return self._run_awaitable_inline(self._awaitable_with_timeout(result, timeout))
        if timeout is not None:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError()
        return result

    @staticmethod
    async def _awaitable_with_timeout(awaitable, timeout: float):
        return await asyncio.wait_for(awaitable, timeout)

    def _ensure_event_subscription(self, run_id: str, since_seq: int = 0, maxsize: int = 0):
        if self._loop is None or not self._loop.is_running():
            return self._job_store.events(run_id, since_seq, maxsize=maxsize)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self._job_store.events(run_id, since_seq, maxsize=maxsize)
        future = asyncio.run_coroutine_threadsafe(
            self._create_event_subscription(run_id, since_seq, maxsize),
            self._loop,
        )
        return future.result()

    async def _create_event_subscription(self, run_id: str, since_seq: int = 0, maxsize: int = 0):
        return self._job_store.events(run_id, since_seq, maxsize=maxsize)

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

    def _attach_event_context(self, event: RuntimeEvent, run_id: str):
        invocation = self._job_store.get_invocation(run_id)
        if invocation is None:
            return
        event.session_id = getattr(invocation, "session_id", None)
        event.parent_run_id = getattr(invocation, "parent_run_id", None)
        event.depth = getattr(invocation, "depth", None)
        event.origin_source = getattr(invocation, "origin_source", None) or getattr(invocation, "source", None)
        event.principal = getattr(invocation, "principal", None)
        event.lock_key = getattr(invocation, "lock_key", None)
        event.command_id = getattr(invocation, "command_id", None)
        event.callable_meta = getattr(invocation, "callable_meta", None)

    def _close_audit_sink(self):
        if self._audit_sink is None:
            return
        self._audit_sink.close()

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
        return self._job_store.pop_run(run_id)

