# Command Line Framework (TTY + Executor + RPC/Web)

[中文](README_zh.md)

## Project Introduction

`python-tty` is a multi-console command framework centered on TTY interaction, with a shared runtime execution model (`Invocation -> Executor -> RuntimeEvent`) that can be reused by RPC/Web frontends.

This repository now includes an official lightweight testing API (`python_tty.testing`) so external projects can test individual command methods without booting the full TTY kernel.

Architecture and module-relationship details were moved out of README and are maintained in [docs/Schema.md](docs/Schema.md).

## Quick Start Example

```python
from python_tty.console_factory import ConsoleFactory

# service can be any business object that commands access via self.console.service
service = object()

factory = ConsoleFactory(service=service)
factory.start()
```

Typical setup flow:
1. Define command classes with `@register_command`.
2. Bind command classes to consoles with `@commands`.
3. Register console topology with `@root` / `@sub` / `@multi`.
4. Start `ConsoleFactory`.

Decorator registration example (`commands`, `root`, `sub`, `multi`):

```python
from prompt_toolkit.styles import Style

from python_tty.commands import BaseCommands
from python_tty.commands.decorators import commands, register_command
from python_tty.consoles import MainConsole, SubConsole, multi, root, sub


class RootCommands(BaseCommands):
    @register_command("ping", "health check")
    def run_ping(self):
        return "pong"


class ModuleCommands(BaseCommands):
    @register_command("status", "module status")
    def run_status(self):
        return "ok"


@root
@commands(RootCommands)
class RootConsole(MainConsole):
    console_name = "root"
    def __init__(self, parent=None, manager=None):
        super().__init__([("class:prompt", "root> ")], Style.from_dict({"": ""}), parent=parent, manager=manager)


@sub("root")
@commands(ModuleCommands)
class ModuleConsole(SubConsole):
    console_name = "module"
    def __init__(self, parent=None, manager=None):
        super().__init__([("class:prompt", "module> ")], Style.from_dict({"": ""}), parent=parent, manager=manager)


@multi({"root": "tools", "module": "tools"})
@commands(ModuleCommands)
class ToolsConsole(SubConsole):
    # runtime names become root_tools / module_tools
    def __init__(self, parent=None, manager=None):
        super().__init__([("class:prompt", "tools> ")], Style.from_dict({"": ""}), parent=parent, manager=manager)
```

## Detailed Configuration Explanation

Configuration entry: `python_tty/config/config.py`.
Top-level type: `Config`.

### ConsoleFactoryConfig

- `run_mode`: `"tty"` or `"concurrent"`.
- `start_executor`: auto start executor during factory startup.
- `executor_in_thread`: in tty mode, run executor loop in a background thread.
- `executor_thread_name`: executor thread name.
- `tty_thread_name`: tty thread name in concurrent mode.
- `shutdown_executor`: shutdown executor when factory stops.

### ExecutorConfig

- `workers`: worker task count.
- `retain_last_n`: keep only last N completed runs.
- `ttl_seconds`: TTL for completed runs.
- `pop_on_wait`: remove run state after wait result.
- `exempt_exceptions`: exceptions treated as cancellation.
- `emit_run_events`: emit state events (`start/success/failure/...`).
- `event_history_max`: max history events per run.
- `event_history_ttl`: history TTL per run.
- `sync_in_threadpool`: run sync handlers in threadpool.
- `threadpool_workers`: threadpool size.
- `audit`: nested `AuditConfig`.

### AuditConfig

- `enabled`: enable audit sink.
- `file_path`: jsonl output file.
- `stream`: output stream (mutually exclusive with `file_path`).
- `async_mode`: async sink writer.
- `flush_interval`: async flush interval.
- `keep_in_memory`: keep records in memory for tests.
- `sink`: custom sink instance.

### RPCConfig

- `enabled`: start gRPC server.
- `bind_host` / `port`: bind address.
- `max_message_bytes`: gRPC payload limit.
- `keepalive_time_ms` / `keepalive_timeout_ms` / `keepalive_permit_without_calls`: keepalive controls.
- `max_concurrent_rpcs`: concurrency limit.
- `max_streams_per_client`: stream fanout limit.
- `stream_backpressure_queue_size`: stream queue size.
- `default_deny`: deny by default when exposure is missing.
- `require_rpc_exposed`: require `exposure.rpc=True`.
- `allowed_principals`: principal allowlist.
- `admin_principals`: admin principal list (allowlist bypass only).
- `require_audit`: require audit for RPC invoke.
- `trust_client_principal`: trust request principal directly.
- `mtls`: nested `MTLSServerConfig`.

### MTLSServerConfig

- `enabled`: enable mTLS.
- `server_cert_file` / `server_key_file`: server cert/key.
- `client_ca_file`: CA bundle for client cert verification.
- `require_client_cert`: enforce client cert.
- `principal_keys`: auth_context keys for principal extraction.

### WebConfig

- `enabled`: start web server.
- `bind_host` / `port`: bind address.
- `root_path`: reverse proxy root path.
- `cors_allow_origins` / `cors_allow_credentials` / `cors_allow_methods` / `cors_allow_headers`: CORS controls.
- `meta_enabled`: enable `/meta` endpoint.
- `meta_cache_control_max_age`: `/meta` cache-control max-age.
- `ws_snapshot_enabled`: enable snapshot websocket.
- `ws_snapshot_include_jobs`: include running jobs in snapshots.
- `ws_max_connections`: websocket connection limit.
- `ws_heartbeat_interval`: heartbeat interval.
- `ws_send_queue_size`: websocket send queue size.

## Testing API Usage Examples

Public imports:

```python
from python_tty.testing import (
    tty_testable,
    discover_tests,
    CommandHarness,
    InvocationHarness,
    TestRunResult,
)
```

### 1. Mark command class or command method

```python
from python_tty.commands import BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.testing import tty_testable

@tty_testable(component="smoke")
class UserCommands(BaseCommands):
    @register_command("ping", "health check")
    def run_ping(self):
        return "pong"

class PartialCommands(BaseCommands):
    @tty_testable(component="critical")
    @register_command("login", "login flow")
    def run_login(self, username):
        return username

    @register_command("debug", "not included unless explicitly selected")
    def run_debug(self):
        return "debug"
```

### 2. Explicit discovery (test-only, no startup auto-scan)

```python
import my_project.commands as command_module
from python_tty.testing import discover_tests

suite = discover_tests(command_module)
all_cases = suite.list_cases()

case = suite.get_case("cmd:usercommands:ping")

# explicit selection still works without decorators
explicit_suite = discover_tests(
    command_module,
    command_ids=["cmd:partialcommands:debug"],
)
```

### 3. Run a command with CommandHarness

```python
from types import SimpleNamespace
from python_tty.testing import CommandHarness

harness = CommandHarness(service=SimpleNamespace(name="svc"), suite=suite)
result: TestRunResult = harness.run("cmd:usercommands:ping")

assert result.ok
assert result.return_value == "pong"
```

### 4. Toggle validation on/off

```python
# validator enabled
result_on = harness.run("cmd:partialcommands:login", argv=[], validate=True)
assert result_on.ok is False
assert result_on.validator_ran is True

# validator disabled
result_off = harness.run("cmd:partialcommands:login", argv=[], validate=False)
assert result_off.validator_ran is False
```

### 5. Run through InvocationHarness runtime path

```python
inv_harness = InvocationHarness(suite=suite)

# direct runtime binding execution
direct_result = inv_harness.run("cmd:usercommands:ping", through_executor=False)

# executor-backed execution (captures state/runtime events)
executor_result = inv_harness.run("cmd:usercommands:ping", through_executor=True)
```

### 6. Inspect TestRunResult

```python
result = inv_harness.run("cmd:usercommands:ping", through_executor=True)

print(result.ok)
print(result.return_value)
print(result.exception)
print(result.outputs)        # normalized output records
print(result.runtime_events) # raw RuntimeEvent objects
print(result.run_id)
```
