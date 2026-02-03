import asyncio
from typing import Optional

import grpc
from google.protobuf import json_format, struct_pb2

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import COMMAND_REGISTRY
from python_tty.config import RPCConfig
from python_tty.consoles.registry import REGISTRY
from python_tty.executor.execution import ExecutionBinding, ExecutionContext
from python_tty.runtime.events import RuntimeEventKind


def _require_generated():
    try:
        from python_tty.frontends.rpc import runtime_pb2, runtime_pb2_grpc
    except Exception as exc:  # pragma: no cover - generated modules may be absent in dev
        raise RuntimeError("runtime_pb2/runtime_pb2_grpc not found; run protoc first.") from exc
    return runtime_pb2, runtime_pb2_grpc


def _struct_to_dict(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, struct_pb2.Struct) and not value.fields:
        return {}
    return json_format.MessageToDict(value, preserving_proto_field_name=True)


def _payload_to_struct(payload):
    if payload is None:
        return struct_pb2.Struct()
    if isinstance(payload, struct_pb2.Struct):
        return payload
    if isinstance(payload, dict):
        return json_format.ParseDict(payload, struct_pb2.Struct())
    return json_format.ParseDict({"value": payload}, struct_pb2.Struct())


def _normalize_console_command(ctx: ExecutionContext):
    if ctx.command_id and (ctx.console_name is None or ctx.command_name is None):
        if ctx.command_id.startswith("cmd:"):
            parts = ctx.command_id.split(":", 2)
            if len(parts) == 3:
                if ctx.console_name is None:
                    ctx.console_name = parts[1] or None
                if ctx.command_name is None:
                    ctx.command_name = parts[2] or None


def _runtime_kind_to_proto(kind):
    if kind is None:
        return None
    try:
        return RuntimeEventKind(kind)
    except ValueError:
        return None


def _level_to_int(level) -> int:
    if level is None:
        return 0
    return int(getattr(level, "value", level))


class RuntimeService:
    # grpc aio will treat this as a servicer when registered via add_*_to_server
    def __init__(self, executor, service=None, manager=None, config: Optional[RPCConfig] = None):
        self._executor = executor
        self._service = service
        self._manager = manager
        self._config = config or RPCConfig()

    async def Invoke(self, request, context):
        runtime_pb2, _ = _require_generated()
        principal = _resolve_principal(request, context, self._config)
        ctx = ExecutionContext(
            source="rpc",
            principal=principal,
            console_name=request.console_name or None,
            command_id=request.command_id or None,
            command_name=request.command_name or None,
            argv=list(request.argv),
            kwargs=_struct_to_dict(request.kwargs),
            raw_cmd=request.raw_cmd or None,
            timeout_ms=request.timeout_ms or None,
            lock_key=request.lock_key or "global",
            session_id=request.session_id or None,
            meta_revision=request.meta_revision or None,
            audit_policy="force",
        )
        _normalize_console_command(ctx)
        if self._config.require_audit and self._executor.audit_sink is None:
            await _abort_failed_precondition(context, "audit sink is required for rpc")
            return
        command_def = _resolve_command_def(ctx)
        if command_def is None:
            await _abort_not_found(context, "command not found")
            return
        if not _is_rpc_allowed(command_def, principal, self._config):
            await _abort_permission_denied(context, "command not allowed for rpc")
            return
        invocation = ctx.to_invocation()
        binding = ExecutionBinding(service=self._service, manager=self._manager, ctx=ctx)
        handler = lambda inv: binding.execute(inv)
        run_id = self._executor.submit(invocation, handler=handler)
        return runtime_pb2.InvokeReply(run_id=run_id)

    async def StreamEvents(self, request, context):
        runtime_pb2, _ = _require_generated()
        if self._executor.job_store.get_run_state(request.run_id) is None:
            await _abort_not_found(context, f"run_id not found: {request.run_id}")
            return
        queue = self._executor.stream_events(
            request.run_id,
            request.since_seq,
            maxsize=self._config.stream_backpressure_queue_size,
        )
        done_event = _build_done_event(context)
        try:
            while True:
                if context.cancelled():
                    break
                event = await _wait_for_event(queue, done_event)
                if event is None:
                    break
                yield runtime_pb2.RuntimeEvent(
                    kind=_kind_to_proto_enum(event),
                    msg="" if event.msg is None else str(event.msg),
                    level=_level_to_int(getattr(event, "level", None)),
                    run_id=getattr(event, "run_id", "") or "",
                    event_type=getattr(event, "event_type", "") or "",
                    payload=_payload_to_struct(getattr(event, "payload", None)),
                    source=getattr(event, "source", "") or "",
                    ts=float(getattr(event, "ts", 0.0) or 0.0),
                    seq=int(getattr(event, "seq", 0) or 0),
                )
                if _is_terminal_event(event):
                    break
        except asyncio.CancelledError:
            return
        finally:
            self._executor.job_store.unsubscribe_events(request.run_id, queue)


def _kind_to_proto_enum(event):
    runtime_pb2, _ = _require_generated()
    kind = _runtime_kind_to_proto(getattr(event, "kind", None))
    if kind == RuntimeEventKind.STATE:
        return runtime_pb2.RUNTIME_EVENT_KIND_STATE
    if kind == RuntimeEventKind.STDOUT:
        return runtime_pb2.RUNTIME_EVENT_KIND_STDOUT
    if kind == RuntimeEventKind.LOG:
        return runtime_pb2.RUNTIME_EVENT_KIND_LOG
    return runtime_pb2.RUNTIME_EVENT_KIND_UNSPECIFIED


def _is_terminal_event(event) -> bool:
    kind = getattr(event, "kind", None)
    event_type = getattr(event, "event_type", None)
    if kind != RuntimeEventKind.STATE:
        return False
    return event_type in {"success", "failure", "cancelled", "timeout"}


def _resolve_command_def(ctx: ExecutionContext):
    console_name = ctx.console_name
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
    if ctx.command_id:
        for command_def in defs:
            if _build_command_id(console_name, command_def.func_name) == ctx.command_id:
                return command_def
    if ctx.command_name:
        for command_def in defs:
            if ctx.command_name in command_def.all_names():
                return command_def
    return None


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"


def _is_rpc_allowed(command_def, principal: Optional[str], config: RPCConfig) -> bool:
    if principal and _is_admin(principal, config):
        return True
    if not _principal_allowed(principal, config):
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


def _resolve_principal(request, context, config: RPCConfig) -> Optional[str]:
    if getattr(request, "principal", None):
        return request.principal
    if hasattr(context, "auth_context"):
        try:
            auth_ctx = context.auth_context()
        except Exception:
            auth_ctx = None
        if auth_ctx:
            for key in config.mtls.principal_keys:
                value = auth_ctx.get(key)
                if not value:
                    continue
                if isinstance(value, (list, tuple)) and value:
                    try:
                        return value[0].decode("utf-8")
                    except Exception:
                        return str(value[0])
                return str(value)
    return None


def _build_done_event(context) -> Optional[asyncio.Event]:
    done_event = asyncio.Event()
    if not hasattr(context, "add_callback"):
        return None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    def _on_done():
        loop.call_soon_threadsafe(done_event.set)

    context.add_callback(_on_done)
    return done_event


async def _wait_for_event(queue: asyncio.Queue, done_event: Optional[asyncio.Event]):
    if done_event is None:
        return await queue.get()
    get_task = asyncio.create_task(queue.get())
    done_task = asyncio.create_task(done_event.wait())
    done, pending = await asyncio.wait(
        {get_task, done_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if done_task in done:
        return None
    return get_task.result()


async def _abort_not_found(context, message: str):
    if hasattr(context, "abort"):
        result = context.abort(grpc.StatusCode.NOT_FOUND, message)
        if asyncio.iscoroutine(result):
            await result
        return
    raise RuntimeError(message)


async def _abort_permission_denied(context, message: str):
    if hasattr(context, "abort"):
        result = context.abort(grpc.StatusCode.PERMISSION_DENIED, message)
        if asyncio.iscoroutine(result):
            await result
        return
    raise RuntimeError(message)


async def _abort_failed_precondition(context, message: str):
    if hasattr(context, "abort"):
        result = context.abort(grpc.StatusCode.FAILED_PRECONDITION, message)
        if asyncio.iscoroutine(result):
            await result
        return
    raise RuntimeError(message)


def add_runtime_service(server, executor, service=None, manager=None):
    runtime_pb2, runtime_pb2_grpc = _require_generated()
    servicer = RuntimeService(executor=executor, service=service, manager=manager)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(servicer, server)
    return servicer


def add_runtime_service_with_config(server, executor, config: RPCConfig, service=None, manager=None):
    runtime_pb2, runtime_pb2_grpc = _require_generated()
    servicer = RuntimeService(executor=executor, service=service, manager=manager, config=config)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(servicer, server)
    return servicer
