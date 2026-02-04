import asyncio
import inspect
import threading
import uuid
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from python_tty.runtime.events import RuntimeEventKind


@dataclass
class CallbackSubscription:
    subscription_id: str
    run_id: str
    task: asyncio.Task
    queue: asyncio.Queue
    on_event: Optional[Callable[[object], None]] = None
    on_done: Optional[Callable[[object], None]] = None


class CallbackRegistry:
    def __init__(self, executor, callback_executor: Optional[Executor] = None):
        self._executor = executor
        self._subs: Dict[str, CallbackSubscription] = {}
        self._lock = threading.Lock()
        self._owns_callback_executor = False
        if callback_executor is not None:
            self._callback_executor = callback_executor
        else:
            self._callback_executor = getattr(executor, "_threadpool", None)
            if self._callback_executor is None:
                self._callback_executor = ThreadPoolExecutor(max_workers=4)
                self._owns_callback_executor = True

    def register(self, run_id: str,
                 on_event: Optional[Callable[[object], None]] = None,
                 on_done: Optional[Callable[[object], None]] = None) -> str:
        loop = getattr(self._executor, "_loop", None)
        if loop is None or not loop.is_running():
            raise RuntimeError("Executor loop is not running")
        subscription_id = str(uuid.uuid4())

        def _create_subscription():
            queue = self._executor.stream_events(run_id)
            task = asyncio.create_task(self._watch(run_id, queue, on_event, on_done, subscription_id))
            sub = CallbackSubscription(
                subscription_id=subscription_id,
                run_id=run_id,
                task=task,
                queue=queue,
                on_event=on_event,
                on_done=on_done,
            )
            with self._lock:
                self._subs[subscription_id] = sub
            return subscription_id

        async def _create_subscription_async():
            return _create_subscription()

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == loop:
            _create_subscription()
            return subscription_id
        return asyncio.run_coroutine_threadsafe(_create_subscription_async(), loop).result()

    def unregister(self, subscription_id: str) -> None:
        with self._lock:
            sub = self._subs.get(subscription_id)
            if sub is None:
                return
            self._subs.pop(subscription_id, None)

        def _cancel():
            sub.task.cancel()
            try:
                self._executor.job_store.unsubscribe_events(sub.run_id, sub.queue)
            except Exception:
                return

        self._run_on_executor_loop(_cancel)

    async def _watch(self, run_id: str, queue: asyncio.Queue,
                     on_event: Optional[Callable[[object], None]],
                     on_done: Optional[Callable[[object], None]],
                     subscription_id: str):
        try:
            while True:
                event = await queue.get()
                if on_event is not None:
                    await self._dispatch_callback(on_event, event)
                if _is_terminal_event(event):
                    if on_done is not None:
                        await self._dispatch_callback(on_done, event)
                    break
        except asyncio.CancelledError:
            raise
        finally:
            try:
                self._executor.job_store.unsubscribe_events(run_id, queue)
            except Exception:
                pass
            with self._lock:
                self._subs.pop(subscription_id, None)

    async def _dispatch_callback(self, func: Callable[[object], None], event: object):
        try:
            if inspect.iscoroutinefunction(func):
                await func(event)
                return
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._callback_executor, func, event)
        except Exception:
            return

    def close(self):
        with self._lock:
            subs = list(self._subs.values())
            self._subs.clear()

        for sub in subs:
            def _cancel(sub=sub):
                sub.task.cancel()
                try:
                    self._executor.job_store.unsubscribe_events(sub.run_id, sub.queue)
                except Exception:
                    return
            self._run_on_executor_loop(_cancel)

        if self._owns_callback_executor:
            try:
                self._callback_executor.shutdown(wait=False)
            except Exception:
                return

    def _run_on_executor_loop(self, func: Callable[[], None]):
        loop = getattr(self._executor, "_loop", None)
        if loop is None or not loop.is_running():
            func()
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == loop:
            func()
            return
        try:
            loop.call_soon_threadsafe(func)
        except Exception:
            return


def _is_terminal_event(event: object) -> bool:
    kind = getattr(event, "kind", None)
    event_type = getattr(event, "event_type", None)
    if kind != RuntimeEventKind.STATE:
        return False
    return event_type in {"success", "failure", "cancelled", "timeout"}
