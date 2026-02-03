import asyncio
from typing import Optional

from google.protobuf import json_format, struct_pb2

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
    def __init__(self, executor, service=None, manager=None):
        self._executor = executor
        self._service = service
        self._manager = manager

    async def Invoke(self, request, context):
        runtime_pb2, _ = _require_generated()
        ctx = ExecutionContext(
            source="rpc",
            principal=request.principal or None,
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
            audit_policy=request.audit_policy or None,
        )
        _normalize_console_command(ctx)
        invocation = ctx.to_invocation()
        binding = ExecutionBinding(service=self._service, manager=self._manager, ctx=ctx)
        handler = lambda inv: binding.execute(inv)
        run_id = self._executor.submit(invocation, handler=handler)
        return runtime_pb2.InvokeReply(run_id=run_id)

    async def StreamEvents(self, request, context):
        runtime_pb2, _ = _require_generated()
        queue = self._executor.job_store.events(request.run_id, request.since_seq)
        try:
            while True:
                if context.cancelled():
                    break
                event = await queue.get()
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
        except asyncio.CancelledError:
            return


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


def add_runtime_service(server, executor, service=None, manager=None):
    runtime_pb2, runtime_pb2_grpc = _require_generated()
    servicer = RuntimeService(executor=executor, service=service, manager=manager)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(servicer, server)
    return servicer
