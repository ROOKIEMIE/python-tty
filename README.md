# Command Line Framework (TTY + Executor + RPC/Web)

[中文](README_zh.md)

This project focuses on the TTY core while providing a unified executor, runtime events, RPC/Web frontends, and session management for complex CLI/TTY apps and lightweight service endpoints.

## Concepts

Console layer:
- `python_tty/consoles/core.py`: `BaseConsole`, `MainConsole`, `SubConsole`
- `python_tty/consoles/manager.py` and `python_tty/consoles/registry.py` for lifecycle and registration

Commands layer:
- `python_tty/commands/core.py`: `BaseCommands`, `CommandValidator`
- `python_tty/commands/registry.py`: `CommandRegistry`, `ArgSpec`
- `python_tty/commands/general.py`: `GeneralValidator`, `GeneralCompleter`
- `python_tty/commands/mixins.py`: `CommandMixin` and built-in mixins

Execution and runtime:
- `python_tty/executor/executor.py`: `CommandExecutor` (unified execution entry)
- `python_tty/runtime/jobs.py`: `JobStore` (RunState/Invocation/event history)
- `python_tty/runtime/events.py`: `RuntimeEvent`, `UIEvent`, `UIEventLevel`
- `python_tty/runtime/router.py`: `proxy_print` and output routing

Session and callbacks:
- `python_tty/session/manager.py`: `SessionManager` (lifecycle + submit + constraints)
- `python_tty/session/store.py`: `SessionStore` (in-memory session state)
- `python_tty/session/callbacks.py`: callback subscriptions (thread-safe cancel)

RPC/Web:
- `python_tty/frontends/rpc`: gRPC Invoke + event streaming
- `python_tty/frontends/web`: FastAPI + WS snapshot (Meta)

Table rendering:
- `python_tty/utils/table.py`: table rendering (auto wrap supported)

TTY / RPC scheduling logic in Executor:
- TTY: builds `Invocation`, submits via `executor.submit_threadsafe()`, workers emit `RuntimeEvent`.
- RPC: builds `Invocation`, enforces exposure/allowlist/audit, `StreamEvents` subscribes to event queues.

## Configuration

Config entry is `python_tty/config/config.py`.

ConsoleFactoryConfig:
- `run_mode`: `"tty"` or `"concurrent"`; decides whether the main thread runs the loop + TTY thread.
- `start_executor`: auto-start executor on factory start.
- `executor_in_thread`: start executor in a background thread in TTY mode.
- `executor_thread_name`: executor loop thread name.
- `tty_thread_name`: TTY thread name in concurrent mode.
- `shutdown_executor`: shutdown executor when factory stops.

ExecutorConfig:
- `workers`: number of workers (execution concurrency).
- `retain_last_n`: keep last N completed runs in memory.
- `ttl_seconds`: TTL for completed runs.
- `pop_on_wait`: drop run state after wait_result.
- `exempt_exceptions`: treat these as cancellation.
- `emit_run_events`: emit start/success/failure state events.
- `event_history_max`: max events per run.
- `event_history_ttl`: TTL for per-run history.
- `sync_in_threadpool`: run sync handlers in a thread pool.
- `threadpool_workers`: max thread pool workers.
- `audit`: `AuditConfig` for audit sink.

AuditConfig:
- `enabled`: enable audit.
- `file_path`: JSONL file output.
- `stream`: stream output (exclusive with file_path).
- `async_mode`: async writer mode.
- `flush_interval`: async flush interval.
- `keep_in_memory`: keep records in memory (tests).
- `sink`: custom AuditSink instance.

RPCConfig:
- `enabled`: start RPC server.
- `bind_host` / `port`: listen address and port.
- `max_message_bytes`: max gRPC message size.
- `keepalive_time_ms` / `keepalive_timeout_ms` / `keepalive_permit_without_calls`: keepalive options.
- `max_concurrent_rpcs`: max RPC concurrency.
- `max_streams_per_client`: max concurrent streams per client.
- `stream_backpressure_queue_size`: per-stream queue limit.
- `default_deny`: deny when exposure is missing.
- `require_rpc_exposed`: require `exposure.rpc=True`.
- `allowed_principals`: principal allowlist.
- `admin_principals`: admin principals (bypass allowlist only).
- `require_audit`: RPC requires audit sink.
- `trust_client_principal`: trust `request.principal` (default False).
- `mtls`: `MTLSServerConfig`.

MTLSServerConfig:
- `enabled`: enable mTLS.
- `server_cert_file` / `server_key_file`: server cert/key.
- `client_ca_file`: client CA bundle.
- `require_client_cert`: require client certs.
- `principal_keys`: auth_context keys for principal extraction.

WebConfig:
- `enabled`: start Web server.
- `bind_host` / `port`: listen address and port.
- `root_path`: reverse-proxy root path.
- `cors_*`: CORS options.
- `meta_enabled`: enable `/meta`.
- `meta_cache_control_max_age`: cache max-age for `/meta`.
- `ws_snapshot_enabled`: enable `/meta/snapshot` websocket.
- `ws_snapshot_include_jobs`: include running job summary.
- `ws_max_connections`: max WS connections.
- `ws_heartbeat_interval`: WS heartbeat seconds.
- `ws_send_queue_size`: WS send queue size.

Factory impact:
- `run_mode="tty"`: TTY runs on main thread; executor can be started in main or background thread.
- `run_mode="concurrent"`: main thread runs asyncio loop; TTY runs in background thread.
- `rpc.enabled=True` / `web.enabled=True`: services are attached during factory startup.
- `start_executor=False`: RPC/Web/Session submit will be unavailable or raise (no executor loop).

## Examples

Quick start (TTY core):
1. Define your consoles and commands (see examples in `python_tty/consoles/examples` and `python_tty/commands/examples`).
2. Ensure console modules are imported so decorators can register them: update `DEFAULT_CONSOLE_MODULES` in `python_tty/consoles/loader.py` or call `load_consoles([...])`.
3. Start the factory:
```python
from python_tty.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

Job/Session basic usage:
```python
from python_tty.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_service)
factory.start_executor()
sm = factory.session_manager

sid = sm.open_session(principal="local")
run_id = sm.submit_command(sid, "cmd:root:help")
result = await sm.result(run_id)
```

Mode A: synchronous orchestration (outer awaits inner)
```python
async def outer():
    inner_id = sm.submit_command(sid, "cmd:root:long_task", await_result=True)
    inner_result = await sm.result(inner_id)
    return inner_result
```

Mode B: async orchestration (callbacks)
```python
def on_event(evt):
    pass

def on_done(evt):
    pass

inner_id = sm.submit_command(sid, "cmd:root:long_task")
sub_id = sm.register_callback(inner_id, on_event=on_event, on_done=on_done)
```

Table rendering:
```python
from python_tty.utils import Table

header = ["name", "status", "detail"]
data = [
    ["job-1", "running", "very long text ..."],
    ["job-2", "done", "short"],
]

table = Table(header, data, title="jobs", wrap=True)
print(table)
```

Single row (debug):
```python
print(table.print_line(["job-3", "queued", "pending"]))
```

## 展望

待定
