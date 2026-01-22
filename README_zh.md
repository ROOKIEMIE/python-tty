# 命令行框架 (V2: Web/RPC 方向)

该分支面向 Web + RPC 能力扩展，目前代码仍以 TTY 核心为主，Web/RPC 尚未落地。

## 快速开始（TTY 核心）

1) 定义 consoles 与 commands（示例见 `src/consoles/examples` 与 `src/commands/examples`）。
2) 确保 console 模块被导入以触发装饰器注册：
   - 修改 `src/consoles/loader.py` 中的 `DEFAULT_CONSOLE_MODULES`，或
   - 手动调用 `load_consoles([...])`。
3) 启动工厂：

```python
from src.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

传入的 `service` 可在 console 中通过 `console.service` 访问，在 commands 中通过 `self.console.service` 访问。若 `service` 未继承 `UIEventSpeaker`，启动时会给出警告。

## 当前能力（TTY 核心）

Console 层：
- `src/consoles/core.py`：`BaseConsole`、`MainConsole`、`SubConsole`
- `src/consoles/manager.py` 与 `src/consoles/registry.py` 负责生命周期与注册

Commands 层：
- `src/commands/core.py`：`BaseCommands`、`CommandValidator`
- `src/commands/registry.py`：`CommandRegistry`、`ArgSpec`
- `src/commands/general.py`：`GeneralValidator`、`GeneralCompleter`
- `src/commands/mixins.py`：`CommandMixin` 及内置 mixins

UI 与工具：
- `src/core/events.py`：`UIEvent`、`UIEventLevel`、`UIEventSpeaker`
- `src/ui/output.py`：`proxy_print`
- `src/utils/`：`tokenize.py`、`table.py`、`ui_logger.py`

## V2 路线图

Web + RPC 规划里程碑：
- M1：Meta Descriptor v1 + Exporter
- M2：RPC proto v1 + 本地序列化/反序列化
- M3：Meta Web Server（HTTP + WS）
- M4：RPC Server（mTLS + allowlist + audit）
- M5：统一执行系统（CommandExecutor）
