# Command Line Framework (V2: Web/RPC-ready)

[中文](README_zh.md)

V2 extends the TTY core toward Web + RPC, while keeping the current codebase focused on the TTY runtime. At the moment, Web/RPC is planned but not yet implemented.

## Quick Start (TTY Core)

1) Define your consoles and commands (see examples in `python_tty/consoles/examples` and `python_tty/commands/examples`).
2) Ensure console modules are imported so decorators can register them:
   - Update `DEFAULT_CONSOLE_MODULES` in `python_tty/consoles/loader.py`, or
   - Call `load_consoles([...])` manually.
3) Start the factory:

```python
from python_tty.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

The `service` instance is available in all consoles via `console.service`, and in commands via `self.console.service`. If `service` does not inherit `UIEventSpeaker`, a warning is emitted at startup.

## Current Capabilities (TTY Core)

Console layer:
- `python_tty/consoles/core.py`: `BaseConsole`, `MainConsole`, `SubConsole`
- `python_tty/consoles/manager.py` and `python_tty/consoles/registry.py` for lifecycle and registration

Commands layer:
- `python_tty/commands/core.py`: `BaseCommands`, `CommandValidator`
- `python_tty/commands/registry.py`: `CommandRegistry`, `ArgSpec`
- `python_tty/commands/general.py`: `GeneralValidator`, `GeneralCompleter`
- `python_tty/commands/mixins.py`: `CommandMixin` and built-in mixins

UI and utilities:
- `python_tty/core/events.py`: `UIEvent`, `UIEventLevel`, `UIEventSpeaker`
- `python_tty/ui/output.py`: `proxy_print`
- `python_tty/utils/`: `tokenize.py`, `table.py`, `ui_logger.py`

## Roadmap (V2)

Planned milestones for Web + RPC:
- M1: Meta Descriptor v1 + Exporter
- M2: RPC proto v1 + local (de)serialization
- M3: Meta Web Server (HTTP + WS)
- M4: RPC Server (mTLS + allowlist + audit)
- M5: Unified execution system (CommandExecutor)
