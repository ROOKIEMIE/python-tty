# 命令行框架（TTY + Executor + RPC/Web）

[English](README.md)

## 项目介绍

`python-tty` 是一个以 TTY 交互为核心的多控制台命令框架，采用统一运行时执行模型（`Invocation -> Executor -> RuntimeEvent`），并可复用到 RPC/Web 前端。

当前版本包含官方轻量测试 API（`python_tty.testing`），可让外部项目在不启动完整 TTY 内核的前提下测试单个命令方法。

架构和模块关系说明已从 README 拆分到 [docs/Schema.md](docs/Schema.md)。

## 快速开始示例

```python
from python_tty.console_factory import ConsoleFactory

# service 可以是任意业务对象，命令内通过 self.console.service 使用
service = object()

factory = ConsoleFactory(service=service)
factory.start()
```

典型流程：
1. 使用 `@register_command` 定义命令类。
2. 使用 `@commands` 将命令类绑定到 console。
3. 使用 `@root` / `@sub` / `@multi` 声明 console 拓扑关系。
4. 启动 `ConsoleFactory`。

装饰器注册示例（`commands`、`root`、`sub`、`multi`）：

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
    # 运行时名称会是 root_tools / module_tools
    def __init__(self, parent=None, manager=None):
        super().__init__([("class:prompt", "tools> ")], Style.from_dict({"": ""}), parent=parent, manager=manager)
```

## 详细配置说明

配置入口：`python_tty/config/config.py`。
顶层类型：`Config`。

### ConsoleFactoryConfig

- `run_mode`：`"tty"` 或 `"concurrent"`。
- `start_executor`：Factory 启动时是否自动启动 executor。
- `executor_in_thread`：tty 模式下是否在后台线程运行 executor loop。
- `executor_thread_name`：executor 线程名。
- `tty_thread_name`：concurrent 模式下 tty 线程名。
- `shutdown_executor`：Factory 关闭时是否关闭 executor。

### ExecutorConfig

- `workers`：worker 数量。
- `retain_last_n`：仅保留最近 N 个完成 run。
- `ttl_seconds`：完成 run 的 TTL。
- `pop_on_wait`：等待结果后是否移除 run 状态。
- `exempt_exceptions`：视为取消的异常类型。
- `emit_run_events`：是否发出 `start/success/failure/...` 状态事件。
- `event_history_max`：每个 run 的历史事件上限。
- `event_history_ttl`：每个 run 的历史事件 TTL。
- `sync_in_threadpool`：同步 handler 是否放入线程池执行。
- `threadpool_workers`：线程池大小。
- `audit`：内嵌 `AuditConfig`。

### AuditConfig

- `enabled`：是否开启审计。
- `file_path`：jsonl 输出文件。
- `stream`：输出流（与 `file_path` 二选一）。
- `async_mode`：是否异步写入。
- `flush_interval`：异步 flush 间隔。
- `keep_in_memory`：测试时保留内存记录。
- `sink`：自定义 sink 实例。

### RPCConfig

- `enabled`：是否启动 gRPC 服务。
- `bind_host` / `port`：监听地址。
- `max_message_bytes`：gRPC 消息大小上限。
- `keepalive_time_ms` / `keepalive_timeout_ms` / `keepalive_permit_without_calls`：keepalive 参数。
- `max_concurrent_rpcs`：并发 RPC 上限。
- `max_streams_per_client`：每客户端 stream 上限。
- `stream_backpressure_queue_size`：stream 队列大小。
- `default_deny`：未声明 exposure 时默认拒绝。
- `require_rpc_exposed`：要求 `exposure.rpc=True`。
- `allowed_principals`：principal allowlist。
- `admin_principals`：管理员 principal 列表（仅绕过 allowlist）。
- `require_audit`：RPC 调用要求审计。
- `trust_client_principal`：是否信任请求内 principal。
- `mtls`：内嵌 `MTLSServerConfig`。

### MTLSServerConfig

- `enabled`：是否启用 mTLS。
- `server_cert_file` / `server_key_file`：服务端证书/私钥。
- `client_ca_file`：客户端证书校验 CA。
- `require_client_cert`：是否强制客户端证书。
- `principal_keys`：从 auth_context 提取 principal 的 key 列表。

### WebConfig

- `enabled`：是否启动 Web 服务。
- `bind_host` / `port`：监听地址。
- `root_path`：反向代理根路径。
- `cors_allow_origins` / `cors_allow_credentials` / `cors_allow_methods` / `cors_allow_headers`：CORS 参数。
- `meta_enabled`：是否启用 `/meta`。
- `meta_cache_control_max_age`：`/meta` 缓存时长。
- `ws_snapshot_enabled`：是否启用 snapshot websocket。
- `ws_snapshot_include_jobs`：snapshot 是否包含运行中任务摘要。
- `ws_max_connections`：websocket 连接上限。
- `ws_heartbeat_interval`：心跳间隔。
- `ws_send_queue_size`：websocket 发送队列大小。

## Testing API 使用示例

公开导入：

```python
from python_tty.testing import (
    tty_testable,
    discover_tests,
    CommandHarness,
    InvocationHarness,
    TestRunResult,
)
```

### 1. 标记命令类或命令方法

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

    @register_command("debug", "仅在显式选择时纳入")
    def run_debug(self):
        return "debug"
```

### 2. 显式发现（仅测试态，不会启动自动扫描）

```python
import my_project.commands as command_module
from python_tty.testing import discover_tests

suite = discover_tests(command_module)
all_cases = suite.list_cases()

case = suite.get_case("cmd:usercommands:ping")

# 即使未加装饰器，也可通过 command_id 显式选择
explicit_suite = discover_tests(
    command_module,
    command_ids=["cmd:partialcommands:debug"],
)
```

### 3. 使用 CommandHarness 运行单命令

```python
from types import SimpleNamespace
from python_tty.testing import CommandHarness

harness = CommandHarness(service=SimpleNamespace(name="svc"), suite=suite)
result: TestRunResult = harness.run("cmd:usercommands:ping")

assert result.ok
assert result.return_value == "pong"
```

### 4. 切换校验开关

```python
# 开启校验
result_on = harness.run("cmd:partialcommands:login", argv=[], validate=True)
assert result_on.ok is False
assert result_on.validator_ran is True

# 关闭校验
result_off = harness.run("cmd:partialcommands:login", argv=[], validate=False)
assert result_off.validator_ran is False
```

### 5. 使用 InvocationHarness 走运行时调用路径

```python
inv_harness = InvocationHarness(suite=suite)

# 直接走 runtime binding 执行
direct_result = inv_harness.run("cmd:usercommands:ping", through_executor=False)

# 通过 executor 执行（可捕获状态/运行时事件）
executor_result = inv_harness.run("cmd:usercommands:ping", through_executor=True)
```

### 6. 检查 TestRunResult

```python
result = inv_harness.run("cmd:usercommands:ping", through_executor=True)

print(result.ok)
print(result.return_value)
print(result.exception)
print(result.outputs)        # 规范化输出记录
print(result.runtime_events) # 原始 RuntimeEvent 列表
print(result.run_id)
```
