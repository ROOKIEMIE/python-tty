# Command Line Framework (TTY, V1)

[中文](README_zh.md)

V1 is a pure TTY framework built on prompt_toolkit. It focuses on a multi-console model, command registration, completion, and validation.

## Quick Start

1) Define your consoles and commands (see examples in `src/consoles/examples` and `src/commands/examples`).
2) Make sure console modules are imported so decorators can register them:
   - Update `DEFAULT_CONSOLE_MODULES` in `src/consoles/loader.py`, or
   - Call `load_consoles([...])` manually before starting.
3) Start the factory:

```python
from src.console_factory import ConsoleFactory

factory = ConsoleFactory(service=my_business_core)
factory.start()
```

The `service` instance is available in all consoles via `console.service`, and in commands via `self.console.service`. If `service` does not inherit `UIEventSpeaker`, a warning is emitted at startup.

## Console Layer

Core classes live in `src/consoles/core.py`:
- `BaseConsole`, `MainConsole`, `SubConsole`
- Each console owns one PromptSession and integrates a Commands instance.

Console registration and lifecycle:
- Decorators: `src/consoles/decorators.py` (`@root`, `@sub`, `@multi`)
- Registry: `src/consoles/registry.py`
- Manager: `src/consoles/manager.py`

## Commands Layer

Core commands logic lives in `src/commands/core.py` with:
- `BaseCommands` (command wiring)
- `CommandValidator` (console-level validation)

Registration and metadata:
- Decorator: `src/commands/decorators.py` (`@register_command`)
- Registry + ArgSpec: `src/commands/registry.py`

Completion and validation helpers:
- `src/commands/general.py` (`GeneralValidator`, `GeneralCompleter`, adapters)

Mixins and core command classification:
- `src/commands/mixins.py` defines `CommandMixin` and built-in mixins.
- Any mixin that inherits `CommandMixin` is treated as a core command in `help`.
- Users can define custom mixins to extend core commands.

## UI Events

Event model:
- `src/core/events.py` (`UIEvent`, `UIEventLevel`, `UIEventSpeaker`)

Output helper:
- `src/ui/output.py` (`proxy_print`)

## Utils

Utilities live in `src/utils`:
- `table.py` for simple ASCII tables
- `tokenize.py` for command parsing helpers
- `ui_logger.py` for logging to the TTY output
