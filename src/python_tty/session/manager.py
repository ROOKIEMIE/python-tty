import asyncio
import inspect
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import COMMAND_REGISTRY
from python_tty.config import RPCConfig
from python_tty.consoles.registry import REGISTRY
from python_tty.executor.execution import ExecutionBinding, ExecutionContext
from python_tty.executor.models import Invocation, RunStatus
from python_tty.runtime.context import get_current_run_id, get_current_source
from python_tty.session.callbacks import CallbackRegistry
from python_tty.session.models import SessionState
from python_tty.session.policy import SessionPolicy
from python_tty.session.store import SessionStore


class SessionManager:
    """Session-aware wrapper around the command executor."""
    def __init__(self, executor, service=None, manager=None,
                 store: Optional[SessionStore] = None,
                 default_policy: Optional[SessionPolicy] = None,
                 rpc_config: Optional[RPCConfig] = None):
        self._executor = executor
        self._service = service
        self._manager = manager
        self._store = store or SessionStore()
        self._default_policy = default_policy or SessionPolicy()
        self._callbacks = CallbackRegistry(executor)
        self._rpc_config = rpc_config or RPCConfig()

    @property
    def store(self) -> SessionStore:
        return self._store

    def open_session(self, principal: str,
                     policy: Optional[SessionPolicy] = None,
                     tags: Optional[Dict[str, Any]] = None) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        state = SessionState(
            session_id=session_id,
            principal=principal,
            created_at=now,
            last_activity_at=now,
            status="OPEN",
            policy=policy or SessionPolicy(
                default_lock_key_mode=self._default_policy.default_lock_key_mode,
                max_concurrent_runs=self._default_policy.max_concurrent_runs,
                default_timeout_ms=self._default_policy.default_timeout_ms,
                idle_ttl_seconds=self._default_policy.idle_ttl_seconds,
            ),
            tags=dict(tags or {}),
        )
        self._store.create(state)
        return session_id

    def close_session(self, session_id: str) -> None:
        state = self._require_session(session_id)
        if state.status == "CLOSED":
            return
        self._store.close(session_id, status="CLOSED")

    def get_session(self, session_id: str) -> SessionState:
        return self._require_session(session_id)

    def list_sessions(self, filters: Optional[Dict[str, Any]] = None):
        return self._store.list(filters=filters)

    def gc_sessions(self):
        return self._store.gc()

    def submit_command(self, session_id: str, command_id: str,
                       argv=None, kwargs=None,
                       timeout_ms: Optional[int] = None,
                       lock_key: Optional[str] = None,
                       await_result: bool = False) -> str:
        state = self._require_session(session_id)
        self._ensure_session_open(state)
        self._store.touch(session_id)
        current_run_id, parent_invocation = self._resolve_parent_invocation()
        origin_source = self._resolve_origin_source(parent_invocation)
        source = self._resolve_source(origin_source)
        self._enforce_rpc_constraints(origin_source, current_run_id, parent_invocation, is_callable=False)
        command_ctx = self._parse_command_id(command_id)
        if origin_source == "rpc":
            self._assert_rpc_command_allowed(command_ctx, state.principal)
            if self._rpc_config.require_audit and self._executor.audit_sink is None:
                raise PermissionError("Audit sink is required for rpc-origin submit")
        self._assert_concurrency_limit(state)
        lock_key = self._resolve_lock_key(lock_key, state, current_run_id)
        self._detect_nested_deadlock(parent_invocation, lock_key, await_result)
        timeout_ms = self._resolve_timeout(timeout_ms, state)
        ctx = ExecutionContext(
            source=source,
            principal=state.principal,
            console_name=command_ctx.get("console_name"),
            command_id=command_id,
            command_name=command_ctx.get("command_name"),
            argv=list(argv or []),
            kwargs=dict(kwargs or {}),
            timeout_ms=timeout_ms,
            lock_key=lock_key,
            session_id=session_id,
            parent_run_id=current_run_id,
            origin_source=origin_source,
            depth=self._resolve_depth(parent_invocation),
            audit_policy="force" if origin_source == "rpc" else None,
        )
        invocation = ctx.to_invocation()
        binding = ExecutionBinding(service=self._service, manager=self._manager, ctx=ctx)
        handler = lambda inv: binding.execute(inv)
        run_id = self._executor.submit_threadsafe(invocation, handler=handler)
        self._store.add_run(session_id, run_id)
        self._trim_runs(state)
        return run_id

    def submit_callable(self, session_id: str, func,
                        *, name: Optional[str] = None,
                        timeout_ms: Optional[int] = None,
                        lock_key: Optional[str] = None,
                        tags: Optional[Dict[str, Any]] = None,
                        await_result: bool = False) -> str:
        state = self._require_session(session_id)
        self._ensure_session_open(state)
        self._store.touch(session_id)
        current_run_id, parent_invocation = self._resolve_parent_invocation()
        origin_source = self._resolve_origin_source(parent_invocation)
        self._enforce_rpc_constraints(origin_source, current_run_id, parent_invocation, is_callable=True)
        source = self._resolve_source(origin_source)
        self._assert_concurrency_limit(state)
        lock_key = self._resolve_lock_key(lock_key, state, current_run_id)
        self._detect_nested_deadlock(parent_invocation, lock_key, await_result)
        timeout_ms = self._resolve_timeout(timeout_ms, state)
        invocation = Invocation(
            source=source,
            principal=state.principal,
            command_id="__callable__",
            argv=[],
            kwargs={},
            timeout_ms=timeout_ms,
            lock_key=lock_key,
            session_id=session_id,
            parent_run_id=current_run_id,
            origin_source=origin_source,
            depth=self._resolve_depth(parent_invocation),
            callable_meta=_build_callable_meta(func, name=name, tags=tags),
        )
        handler = _wrap_callable(func)
        run_id = self._executor.submit_threadsafe(invocation, handler=handler)
        self._store.add_run(session_id, run_id)
        self._trim_runs(state)
        return run_id

    async def stream_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[object]:
        queue = self._executor.stream_events(run_id, since_seq=since_seq)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._executor.job_store.unsubscribe_events(run_id, queue)

    async def result(self, run_id: str, timeout_ms: Optional[int] = None):
        if timeout_ms is None:
            return await self._executor.wait_result(run_id)
        return await asyncio.wait_for(self._executor.wait_result(run_id), timeout_ms / 1000.0)

    def get_run(self, run_id: str):
        return self._executor.job_store.get_run_state(run_id)

    def cancel(self, run_id: str):
        return self._executor.cancel(run_id)

    def register_callback(self, run_id: str,
                          on_event=None,
                          on_done=None) -> str:
        return self._callbacks.register(run_id, on_event=on_event, on_done=on_done)

    def unregister_callback(self, subscription_id: str) -> None:
        self._callbacks.unregister(subscription_id)

    def _require_session(self, session_id: str) -> SessionState:
        state = self._store.get(session_id)
        if state is None:
            raise KeyError(f"Session not found: {session_id}")
        return state

    @staticmethod
    def _ensure_session_open(state: SessionState):
        if state.status == "OPEN":
            return
        raise RuntimeError(f"Session is not open: {state.session_id} ({state.status})")

    def _resolve_parent_invocation(self):
        current_run_id = get_current_run_id()
        if current_run_id is None:
            return None, None
        invocation = self._executor.job_store.get_invocation(current_run_id)
        return current_run_id, invocation

    def _resolve_origin_source(self, parent_invocation: Optional[Invocation]) -> str:
        if parent_invocation is not None:
            return getattr(parent_invocation, "origin_source", None) or parent_invocation.source
        return get_current_source() or "internal"

    @staticmethod
    def _resolve_source(origin_source: str) -> str:
        return get_current_source() or origin_source or "internal"

    @staticmethod
    def _resolve_depth(parent_invocation: Optional[Invocation]) -> int:
        if parent_invocation is None:
            return 0
        return int(getattr(parent_invocation, "depth", 0) or 0) + 1

    @staticmethod
    def _resolve_timeout(timeout_ms: Optional[int], state: SessionState) -> Optional[int]:
        if timeout_ms is not None:
            return timeout_ms
        return state.policy.default_timeout_ms

    def _resolve_lock_key(self, lock_key: Optional[str], state: SessionState,
                          current_run_id: Optional[str]) -> str:
        if lock_key is not None:
            return lock_key
        if current_run_id is not None:
            return f"child:{current_run_id}"
        mode = state.policy.default_lock_key_mode
        if mode == "session":
            return f"session:{state.session_id}"
        if mode == "global":
            return "global"
        return ""

    def _detect_nested_deadlock(self, parent_invocation: Optional[Invocation],
                                lock_key: str, await_result: bool):
        if not await_result:
            return
        if parent_invocation is None:
            return
        outer_lock_key = getattr(parent_invocation, "lock_key", None)
        if not outer_lock_key or not lock_key:
            return
        if lock_key != outer_lock_key:
            return
        if not str(lock_key).startswith("session:"):
            return
        raise RuntimeError(
            "Nested submit with same session lock may deadlock; "
            "use lock_key='child:<outer_run_id>' or leave lock_key unset to auto-derive."
        )

    def _assert_concurrency_limit(self, state: SessionState):
        limit = state.policy.max_concurrent_runs
        if limit is None or limit <= 0:
            return
        active = 0
        for run_id in list(state.run_ids):
            run_state = self._executor.job_store.get_run_state(run_id)
            if run_state is None:
                continue
            if run_state.status in (RunStatus.PENDING, RunStatus.RUNNING):
                active += 1
            if active >= limit:
                raise RuntimeError(f"Session concurrency limit exceeded: {limit}")

    def _trim_runs(self, state: SessionState):
        retain = self._store.retain_last_n()
        if retain is None or retain < 0:
            return
        if len(state.run_ids) <= retain:
            return
        trimmed = []
        for run_id in list(state.run_ids):
            run_state = self._executor.job_store.get_run_state(run_id)
            if run_state is None:
                trimmed.append(run_id)
            elif run_state.status not in (RunStatus.PENDING, RunStatus.RUNNING):
                trimmed.append(run_id)
            if len(state.run_ids) - len(trimmed) <= retain:
                break
        for run_id in trimmed:
            try:
                state.run_ids.remove(run_id)
            except ValueError:
                continue

    def _enforce_rpc_constraints(self, origin_source: str,
                                 current_run_id: Optional[str],
                                 parent_invocation: Optional[Invocation],
                                 is_callable: bool):
        if origin_source != "rpc":
            return
        if current_run_id is not None or parent_invocation is not None:
            raise PermissionError("Nested submit is not allowed in rpc-origin context")
        if is_callable:
            raise PermissionError("Callable submit is not allowed in rpc-origin context")

    def _assert_rpc_command_allowed(self, command_ctx: Dict[str, Optional[str]], principal: Optional[str]):
        command_def = self._resolve_command_def(command_ctx)
        if command_def is None:
            raise ValueError("Command not found")
        if not _is_rpc_allowed(command_def, principal, self._rpc_config):
            raise PermissionError("Command not allowed for rpc-origin submit")

    @staticmethod
    def _parse_command_id(command_id: str) -> Dict[str, Optional[str]]:
        console_name = None
        command_name = None
        if command_id and command_id.startswith("cmd:"):
            parts = command_id.split(":", 2)
            if len(parts) == 3:
                console_name = parts[1] or None
                command_name = parts[2] or None
        return {
            "console_name": console_name,
            "command_name": command_name,
            "command_id": command_id,
        }

    @staticmethod
    def _resolve_command_def(command_ctx: Dict[str, Optional[str]]):
        console_name = command_ctx.get("console_name")
        if console_name is None:
            return None
        console_cls = None
        for name, cls, _ in REGISTRY.iter_consoles():
            if name == console_name:
                console_cls = cls
                break
        if console_cls is None:
            return None
        defs = COMMAND_REGISTRY.get_command_defs_for_console(console_cls)
        if not defs:
            defs = COMMAND_REGISTRY.collect_from_commands_cls(DefaultCommands)
        command_id = command_ctx.get("command_id")
        command_name = command_ctx.get("command_name")
        if command_id:
            for command_def in defs:
                if _build_command_id(console_name, command_def.func_name) == command_id:
                    return command_def
        if command_name:
            for command_def in defs:
                if command_name in command_def.all_names():
                    return command_def
        return None


def _wrap_callable(func):
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return func
    if len(params) == 0:
        return lambda _inv: func()
    return func


def _build_callable_meta(func, name: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
    meta = {
        "name": name or getattr(func, "__name__", "callable"),
        "qualname": getattr(func, "__qualname__", None),
        "module": getattr(func, "__module__", None),
    }
    if tags:
        meta["tags"] = dict(tags)
    return meta


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"


def _is_rpc_allowed(command_def, principal: Optional[str], config: RPCConfig) -> bool:
    is_admin = principal is not None and _is_admin(principal, config)
    if not (is_admin or _principal_allowed(principal, config)):
        return False
    exposure = getattr(command_def, "exposure", None) or {}
    if config.require_rpc_exposed or config.default_deny:
        return bool(exposure.get("rpc", False))
    return True


def _principal_allowed(principal: Optional[str], config: RPCConfig) -> bool:
    if not config.allowed_principals:
        return True
    if principal is None:
        return False
    return principal in config.allowed_principals


def _is_admin(principal: str, config: RPCConfig) -> bool:
    if not config.admin_principals:
        return False
    return principal in config.admin_principals
