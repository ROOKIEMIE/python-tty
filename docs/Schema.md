# 框架架构说明

## 1. 运行时架构概览

`python-tty` 采用分层运行时模型：命令调用意图首先被表达为 `Invocation`，再由 `CommandExecutor` 执行，并通过 `RuntimeEvent` 事件流对外观测。

高层分层：
1. Console / Command 定义层。
2. Runtime 执行层。
3. Session / 回调编排层。
4. 前端适配层（TTY、RPC、Web）。
5. 测试专用命令级能力层（`python_tty.testing`）。

## 2. 模块结构

### Console 与 Command 定义

- `python_tty/consoles/core.py`
  作用：`BaseConsole`、`MainConsole`、`SubConsole` 生命周期与命令分发入口。
- `python_tty/consoles/registry.py`
  作用：console 注册表与树结构构建。
- `python_tty/consoles/manager.py`
  作用：活动 console 栈、切换与 prompt 循环管理。
- `python_tty/commands/core.py`
  作用：`BaseCommands`、命令查找、补全器/校验器装配。
- `python_tty/commands/decorators.py`
  作用：`@register_command` 命令元信息声明。
- `python_tty/commands/registry.py`
  作用：命令元信息统一存储（`CommandInfo` / `CommandDef`）。

### Runtime 与 Executor

- `python_tty/executor/models.py`
  作用：`Invocation`、`RunState`、`RunStatus` 数据模型。
- `python_tty/executor/execution.py`
  作用：`ExecutionContext` + `ExecutionBinding`（调用绑定逻辑）。
- `python_tty/executor/executor.py`
  作用：`CommandExecutor` 提交/等待/取消/事件发布。
- `python_tty/runtime/events.py`
  作用：`RuntimeEvent`、`UIEvent`、事件级别与事件种类。
- `python_tty/runtime/jobs.py`
  作用：运行状态/结果/事件存储（`JobStore`）。
- `python_tty/runtime/router.py`
  作用：`proxy_print` 与 UI/运行时事件路由。

### Session 与前端

- `python_tty/session/*`
  作用：会话生命周期、回调订阅、策略约束。
- `python_tty/frontends/rpc/*`
  作用：gRPC Invoke 与事件流映射。
- `python_tty/frontends/web/*`
  作用：HTTP/WS 快照与元信息暴露。
- `python_tty/console_factory.py`
  作用：manager/executor/frontends 的统一装配入口。

## 3. 关系模型

### Console / Commands / Runtime

1. Console 接收命令文本。
2. 命令文本被标准化为 `ExecutionContext`。
3. `ExecutionContext` 转换为 `Invocation`。
4. `Invocation` 通过 `ExecutionBinding` + `CommandExecutor` 执行（或直接走 binding 路径）。
5. 命令输出与状态变更产出 `RuntimeEvent`。
6. TTY/RPC/Web 消费事件流并进行渲染或传输。

### Executor / Session / Frontends

- `CommandExecutor` 是统一运行时执行中心。
- `SessionManager` 与各前端通过同一 invocation 模型提交执行。
- `JobStore` 持有运行状态、结果与可回放历史事件。

## 4. 测试子系统定位

新增包：`python_tty/testing/`

公开 API：
- `tty_testable`
- `discover_tests`
- `CommandHarness`
- `InvocationHarness`
- `TestRunResult`

设计目标：
- 提供轻量、组件级命令测试能力。
- 复用现有命令注册元数据与运行时 binding 路径。
- 避免强制外部测试实例化 `ConsoleFactory`。

## 5. 测试子系统设计

### 5.1 装饰器（`tty_testable`）

- 可标记 `BaseCommands` 子类。
- 可标记已注册的命令方法。
- 仅写入元数据（`__tty_testable__`、`__tty_test_meta__`）。
- 不触发全局注册、自动扫描或启动副作用。

### 5.2 发现（`discover_tests`）

- 显式发现（不会在生产启动时自动扫描）。
- 支持模块、命令类、方法/对象、`command_id` 显式过滤。
- 基于现有 `CommandRegistry` 元信息构建发现结果。
- 返回稳定 suite/case 结构，包含：
  - `command_id`
  - 命令/console 标识
  - 所属命令类
  - 方法引用
  - class-marked / method-marked 标记
  - 合并后的测试元信息

### 5.3 Harness 分层

#### CommandHarness

- 直接执行单命令。
- 支持注入 `service` 和 `manager` 桩对象。
- 支持每次运行切换校验开关。
- 将输出/事件统一收敛到结果对象。

#### InvocationHarness

- 构建 `ExecutionContext` + `ExecutionBinding` + `Invocation`。
- 支持直接 binding 执行或走 executor（`through_executor=True`）。
- 在可用条件下捕获 executor 状态事件与运行时事件。

### 5.4 结果模型（`TestRunResult`）

统一字段：
- `ok`
- `command_id`
- `return_value`
- `exception`
- `outputs`
- `runtime_events`
- `validator_ran`
- `invocation`
- `run_id`

## 6. 本里程碑边界

本次里程碑仅包含：
- `CommandHarness`
- `InvocationHarness`

刻意延后：
- pytest plugin 集成
- transcript 快照测试体系
- 完整 `KernelHarness`
- 生产启动路径中的标记自动发现

边界原因：
- 首版测试 API 优先保持最小可用、显式可控、低风险。
- 保持现有运行时/启动链路兼容，不引入生产副作用。
- 先满足外部项目“单命令轻量测试”核心诉求，再逐步扩展。
