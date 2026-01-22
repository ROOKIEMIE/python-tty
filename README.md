# Command Line Framework (V2: Web/RPC-ready)

[中文](README_zh.md)

V2 extends the TTY core toward Web + RPC, while keeping the current codebase focused on the TTY runtime. At the moment, Web/RPC is planned but not yet implemented.

## Quick Start (TTY Core)

1) Define your consoles and commands (see examples in `src/consoles/examples` and `src/commands/examples`).
2) Ensure console modules are imported so decorators can register them:
   - Update `DEFAULT_CONSOLE_MODULES` in `src/consoles/loader.py`, or
   - Call `load_consoles([...])` manually.
3) Start the factory:

```python
from src.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

The `service` instance is available in all consoles via `console.service`, and in commands via `self.console.service`. If `service` does not inherit `UIEventSpeaker`, a warning is emitted at startup.

## Current Capabilities (TTY Core)

Console layer:
- `src/consoles/core.py`: `BaseConsole`, `MainConsole`, `SubConsole`
- `src/consoles/manager.py` and `src/consoles/registry.py` for lifecycle and registration

Commands layer:
- `src/commands/core.py`: `BaseCommands`, `CommandValidator`
- `src/commands/registry.py`: `CommandRegistry`, `ArgSpec`
- `src/commands/general.py`: `GeneralValidator`, `GeneralCompleter`
- `src/commands/mixins.py`: `CommandMixin` and built-in mixins

UI and utilities:
- `src/core/events.py`: `UIEvent`, `UIEventLevel`, `UIEventSpeaker`
- `src/ui/output.py`: `proxy_print`
- `src/utils/`: `tokenize.py`, `table.py`, `ui_logger.py`

## Roadmap (V2)

Planned milestones for Web + RPC:
- M1: Meta Descriptor v1 + Exporter
- M2: RPC proto v1 + local (de)serialization
- M3: Meta Web Server (HTTP + WS)
- M4: RPC Server (mTLS + allowlist + audit)
- M5: Unified execution system (CommandExecutor)
