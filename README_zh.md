# 命令行框架（TTY + Executor + RPC/Web）

[English](README.md)

项目以 TTY 交互为核心，提供统一执行器、运行态事件、RPC/Web 前端与会话管理能力，适合构建复杂 CLI/TTY 应用与轻量服务化入口。

## 概念

Console 层：
- `python_tty/consoles/core.py`：`BaseConsole`、`MainConsole`、`SubConsole`
- `python_tty/consoles/manager.py` 与 `python_tty/consoles/registry.py` 负责生命周期与注册

Commands 层：
- `python_tty/commands/core.py`：`BaseCommands`、`CommandValidator`
- `python_tty/commands/registry.py`：`CommandRegistry`、`ArgSpec`
- `python_tty/commands/general.py`：`GeneralValidator`、`GeneralCompleter`
- `python_tty/commands/mixins.py`：`CommandMixin` 及内置 mixins

执行与运行态：
- `python_tty/executor/executor.py`：`CommandExecutor`（统一运行入口）
- `python_tty/runtime/jobs.py`：`JobStore`（RunState/Invocation/事件历史）
- `python_tty/runtime/events.py`：`RuntimeEvent`、`UIEvent`、`UIEventLevel`
- `python_tty/runtime/router.py`：`proxy_print` 与输出路由

会话与回调：
- `python_tty/session/manager.py`：`SessionManager`（会话生命周期 + submit + 约束）
- `python_tty/session/store.py`：`SessionStore`（内存会话状态）
- `python_tty/session/callbacks.py`：回调订阅（线程安全取消）

RPC/Web：
- `python_tty/frontends/rpc`：gRPC Invoke + 事件流
- `python_tty/frontends/web`：FastAPI + WS snapshot（Meta）

表格渲染：
- `python_tty/utils/table.py`：表格渲染（支持自动折行）

TTY / RPC 在 Executor 中的调度逻辑：
- TTY：构造 `Invocation`，通过 `executor.submit_threadsafe()` 提交，worker 执行并产出 `RuntimeEvent`。
- RPC：构造 `Invocation`，强制审计与 exposure/allowlist 校验后提交，`StreamEvents` 订阅事件队列。

## 配置

Config 入口在 `python_tty/config/config.py`。

ConsoleFactoryConfig：
- `run_mode`: `"tty"` 或 `"concurrent"`，决定是否在主线程跑 loop + TTY 子线程。
- `start_executor`: 启动时是否自动启动 executor（影响 TTY/RPC/Web 是否可用）。
- `executor_in_thread`: TTY 模式下 executor 是否在后台线程运行。
- `executor_thread_name`: executor loop 线程名。
- `tty_thread_name`: concurrent 模式下 TTY 线程名。
- `shutdown_executor`: Factory 关闭时是否自动关闭 executor。

ExecutorConfig：
- `workers`: worker 数量，决定并发执行能力。
- `retain_last_n`: 内存中保留最近 N 条完成 run。
- `ttl_seconds`: 完成 run 的超时回收时间。
- `pop_on_wait`: `wait_result` 后是否移除 run。
- `exempt_exceptions`: 视为取消的异常类型。
- `emit_run_events`: 是否产生 start/success/failure 等状态事件。
- `event_history_max`: 每个 run 的事件缓存上限。
- `event_history_ttl`: 每个 run 的事件缓存 TTL。
- `sync_in_threadpool`: 同步 handler 是否进线程池。
- `threadpool_workers`: 同步线程池大小。
- `audit`: `AuditConfig` 审计配置。

AuditConfig：
- `enabled`: 启用审计。
- `file_path`: JSONL 文件路径。
- `stream`: 写入的 stream（与 file_path 二选一）。
- `async_mode`: 异步写入。
- `flush_interval`: 异步 flush 间隔。
- `keep_in_memory`: 内存缓冲（测试用）。
- `sink`: 自定义 AuditSink。

RPCConfig：
- `enabled`: 是否启动 RPC server。
- `bind_host` / `port`: 监听地址与端口。
- `max_message_bytes`: 最大消息大小。
- `keepalive_time_ms` / `keepalive_timeout_ms` / `keepalive_permit_without_calls`: keepalive 参数。
- `max_concurrent_rpcs`: RPC 并发上限。
- `max_streams_per_client`: 单客户端并发 stream 上限。
- `stream_backpressure_queue_size`: 每个 stream 的队列上限。
- `default_deny`: exposure 未设置时默认拒绝。
- `require_rpc_exposed`: 必须 `exposure.rpc=True` 才可 Invoke。
- `allowed_principals`: principal allowlist。
- `admin_principals`: 管理员 principal（仅绕过 allowlist，不绕过 exposure）。
- `require_audit`: RPC 必须启用审计。
- `trust_client_principal`: 是否信任 `request.principal`（默认 False）。
- `mtls`: `MTLSServerConfig`。

MTLSServerConfig：
- `enabled`: 是否启用 mTLS。
- `server_cert_file` / `server_key_file`: 服务端证书与私钥。
- `client_ca_file`: 客户端 CA。
- `require_client_cert`: 是否强制客户端证书。
- `principal_keys`: 从 auth_context 提取 principal 的 key 列表。

WebConfig：
- `enabled`: 是否启动 Web server。
- `bind_host` / `port`: 监听地址与端口。
- `root_path`: 反向代理根路径。
- `cors_*`: CORS 配置。
- `meta_enabled`: `/meta` 开关。
- `meta_cache_control_max_age`: `/meta` 缓存秒数。
- `ws_snapshot_enabled`: `/meta/snapshot` WS 开关。
- `ws_snapshot_include_jobs`: 是否包含运行中任务摘要。
- `ws_max_connections`: WS 最大连接数。
- `ws_heartbeat_interval`: WS 心跳间隔。
- `ws_send_queue_size`: WS 发送队列大小。

对 Factory 启动的影响：
- `run_mode="tty"`: TTY 在主线程运行；executor 可在后台线程或主线程启动。
- `run_mode="concurrent"`: 主线程跑 asyncio loop，TTY 在后台线程运行；RPC/Web 与 executor 挂在主 loop。
- `rpc.enabled=True` / `web.enabled=True`: 会在 Factory 启动阶段挂载 RPC/Web 服务。
- `start_executor=False`: RPC/Web/Session submit 会不可用或抛错（依赖 executor loop）。

## 示例

快速开始（TTY 核心）：
1. 定义 consoles 与 commands（示例见 `python_tty/consoles/examples` 与 `python_tty/commands/examples`）。
2. 确保 console 模块被导入以触发装饰器注册：修改 `python_tty/consoles/loader.py` 中的 `DEFAULT_CONSOLE_MODULES`，或手动调用 `load_consoles([...])`。
3. 启动工厂：
```python
from python_tty.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

Job/Session 基本使用：
```python
from python_tty.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_service)
factory.start_executor()
sm = factory.session_manager

sid = sm.open_session(principal="local")
run_id = sm.submit_command(sid, "cmd:root:help")
result = await sm.result(run_id)
```

模式 A：同步编排（外层 await 内层）：
```python
async def outer():
    inner_id = sm.submit_command(sid, "cmd:root:long_task", await_result=True)
    inner_result = await sm.result(inner_id)
    return inner_result
```

模式 B：异步编排（回调消费）：
```python
def on_event(evt):
    pass

def on_done(evt):
    pass

inner_id = sm.submit_command(sid, "cmd:root:long_task")
sub_id = sm.register_callback(inner_id, on_event=on_event, on_done=on_done)
```

Table 渲染示例：
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

单行渲染（调试）：
```python
print(table.print_line(["job-3", "queued", "pending"]))
```

## 展望

待定
