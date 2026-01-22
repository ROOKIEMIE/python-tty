# 命令行框架 (TTY, V1)

该分支为纯TTY框架，基于 prompt_toolkit 构建，专注于多级Console、命令注册、补全与校验。

## 快速开始

1) 定义你的 consoles 和 commands（示例见 `src/consoles/examples` 与 `src/commands/examples`）。
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

## Console 部分

核心类位于 `src/consoles/core.py`：
- `BaseConsole`、`MainConsole`、`SubConsole`
- 每个 Console 绑定一个 PromptSession，并组合一个 Commands 实例

注册与生命周期：
- 装饰器：`src/consoles/decorators.py`（`@root`、`@sub`、`@multi`）
- 注册表：`src/consoles/registry.py`
- 管理器：`src/consoles/manager.py`

## Commands 部分

核心逻辑位于 `src/commands/core.py`：
- `BaseCommands`（命令 wiring）
- `CommandValidator`（Console 级校验）

注册与元信息：
- 装饰器：`src/commands/decorators.py`（`@register_command`）
- Registry + ArgSpec：`src/commands/registry.py`

补全与校验基类：
- `src/commands/general.py`（`GeneralValidator`、`GeneralCompleter` 等）

Mixins 与核心命令分类：
- `src/commands/mixins.py` 定义 `CommandMixin` 与内置 mixins
- 继承 `CommandMixin` 的类会被视为核心命令并在 `help` 中归类
- 用户可自定义 mixin 以扩展核心命令

## UI 事件

事件模型：
- `src/core/events.py`（`UIEvent`、`UIEventLevel`、`UIEventSpeaker`）

输出工具：
- `src/ui/output.py`（`proxy_print`）

## Utils 部分

工具位于 `src/utils`：
- `table.py`：ASCII 表格
- `tokenize.py`：命令切分工具
- `ui_logger.py`：将日志输出到 TTY
