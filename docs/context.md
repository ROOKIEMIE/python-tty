# src

## python_tty

### (M)__init\_\_.py

```python
from python_tty.config import Config
from python_tty.console_factory import ConsoleFactory
from python_tty.runtime.events import (
    EventBase,
    RuntimeEvent,
    RuntimeEventKind,
    UIEvent,
    UIEventLevel,
    UIEventListener,
    UIEventSpeaker,
)
from python_tty.runtime.router import proxy_print

__all__ = [
    "UIEvent",
    "UIEventLevel",
    "EventBase",
    "RuntimeEvent",
    "RuntimeEventKind",
    "UIEventListener",
    "UIEventSpeaker",
    "ConsoleFactory",
    "Config",
    "proxy_print",
]
```

### (M)console_factory.py

```python
import asyncio
import threading

from python_tty.config import Config
from python_tty.consoles.loader import load_consoles
from python_tty.consoles.manager import ConsoleManager
from python_tty.consoles.registry import REGISTRY
from python_tty.executor import CommandExecutor
from python_tty.runtime.provider import set_default_router
from python_tty.runtime.router import OutputRouter
from python_tty.runtime.sinks import TTYEventSink


class ConsoleFactory:
    """Bootstrap console system by loading modules and registering consoles.

    Example:
        # Pass your business core instance here to make it available
        # to all console/commands classes via the manager service.
        factory = ConsoleFactory(object())
        factory.start()

    Notes:
        - To auto-load consoles, update DEFAULT_CONSOLE_MODULES in
          python_tty.consoles.loader with the modules that define your console classes.
        - Or call load_consoles(...) yourself before starting to register
          consoles via their decorators.
    """
    def __init__(self, service=None, config: Config = None):
        if config is None:
            config = Config()
        self.config = config
        if self.config.console_manager.output_router is None:
            self.config.console_manager.output_router = OutputRouter()
        set_default_router(self.config.console_manager.output_router)
        self.executor = CommandExecutor(config=config.executor)
        self._executor_loop = None
        self._executor_thread = None
        self._tty_sink = None
        self.manager = ConsoleManager(
            service=service,
            executor=self.executor,
            on_shutdown=self.shutdown,
            config=config.console_manager,
        )
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        run_mode = self.config.console_factory.run_mode
        if run_mode == "tty":
            self._start_executor_if_needed()
            self.manager.run()
            return
        if run_mode == "concurrent":
            self.start_concurrent()
            return
        raise ValueError(f"Unsupported run_mode: {run_mode}")

    def start_concurrent(self):
        """Start executor on the main loop and run TTY in a background thread."""
        loop = asyncio.new_event_loop()
        self._executor_loop = loop
        asyncio.set_event_loop(loop)
        if self.config.console_factory.start_executor:
            self.start_executor(loop=loop)

        def _run_tty():
            try:
                self.manager.run()
            finally:
                if loop.is_running():
                    loop.call_soon_threadsafe(loop.stop)

        tty_thread = threading.Thread(
            target=_run_tty,
            name=self.config.console_factory.tty_thread_name,
            daemon=True,
        )
        tty_thread.start()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def start_executor(self, loop=None):
        """Start executor workers on the provided asyncio loop."""
        self.executor.start(loop=loop)
        active_loop = loop or self._executor_loop or self.executor._loop
        if active_loop is not None:
            self._attach_tty_sink(loop=active_loop)

    def shutdown_executor(self, wait=True, timeout=None):
        """Shutdown executor workers after RPC/TTY stop."""
        loop = self._executor_loop
        if loop is not None and loop.is_running():
            self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)
            loop.call_soon_threadsafe(loop.stop)
            if self._executor_thread is not None and wait:
                self._executor_thread.join(timeout)
            return None
        return self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)

    def shutdown(self):
        """Shutdown all resources owned by the factory."""
        if self.config.console_factory.shutdown_executor:
            self.shutdown_executor()

    def _start_executor_if_needed(self):
        if not self.config.console_factory.start_executor:
            return
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        if self.config.console_factory.executor_in_thread:
            self._start_executor_thread()
        else:
            self.start_executor()

    def _start_executor_thread(self):
        if self._executor_thread is not None and self._executor_thread.is_alive():
            return
        loop = asyncio.new_event_loop()
        self._executor_loop = loop

        def _run_loop():
            asyncio.set_event_loop(loop)
            self.start_executor(loop=loop)
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        self._executor_thread = threading.Thread(
            target=_run_loop,
            name=self.config.console_factory.executor_thread_name,
            daemon=True,
        )
        self._executor_thread.start()

    def _attach_tty_sink(self, loop):
        if self._tty_sink is not None:
            return
        default_router = self.config.console_manager.output_router
        if default_router is None:
            return
        self._tty_sink = TTYEventSink(self.executor.job_store, default_router)
        self._tty_sink.start(loop)
```

### audit

#### (M)__init\_\_.py

```python
from python_tty.audit.sink import AuditSink
from python_tty.audit.ui_logger import ConsoleHandler

__all__ = [
    "AuditSink",
    "ConsoleHandler",
]
```

#### (M)sink.py

```python
import json
import queue
import threading
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Iterable, Optional, TextIO


class AuditSink:
    def __init__(self, file_path: Optional[str] = None, stream: Optional[TextIO] = None,
                 keep_in_memory: bool = False, async_mode: bool = False,
                 flush_interval: float = 1.0):
        if file_path is not None and stream is not None:
            raise ValueError("Only one of file_path or stream can be set")
        self._path = file_path
        self._stream = stream
        self._owns_stream = False
        if self._stream is None and self._path is not None:
            self._stream = open(self._path, "a", encoding="utf-8")
            self._owns_stream = True
        self._buffer = [] if keep_in_memory else None
        self._async_mode = async_mode and self._stream is not None
        self._flush_interval = max(0.1, float(flush_interval))
        self._lock = threading.Lock()
        self._queue = None
        self._stop_event = threading.Event()
        self._worker = None
        if self._async_mode:
            self._queue = queue.Queue()
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="AuditSinkWriter",
                daemon=True,
            )
            self._worker.start()

    @property
    def buffer(self):
        return self._buffer

    def record_invocation(self, invocation):
        self._write("invocation", invocation)

    def record_run_state(self, run_state):
        self._write("run_state", run_state)

    def record_event(self, event):
        self._write("event", event)

    def record_bundle(self, invocation=None, run_state=None, events: Optional[Iterable[Any]] = None):
        if invocation is not None:
            self.record_invocation(invocation)
        if run_state is not None:
            self.record_run_state(run_state)
        if events:
            for event in events:
                self.record_event(event)

    def close(self):
        if self._async_mode and self._worker is not None:
            self._stop_event.set()
            self._worker.join()
        if self._owns_stream and self._stream is not None:
            self._stream.close()
        self._stream = None
        self._owns_stream = False

    def _write(self, record_type: str, data):
        record = {
            "type": record_type,
            "ts": time.time(),
            "data": self._materialize(data),
        }
        if self._buffer is not None:
            self._buffer.append(record)
        if self._stream is None:
            return
        if self._async_mode and self._queue is not None:
            self._queue.put(record)
            return
        self._write_record(record)

    def _write_record(self, record):
        payload = json.dumps(record, default=self._json_default)
        with self._lock:
            if self._stream is None:
                return
            self._stream.write(payload + "\n")
            self._stream.flush()

    def _write_batch(self, records):
        payload = "\n".join(json.dumps(record, default=self._json_default) for record in records) + "\n"
        with self._lock:
            if self._stream is None:
                return
            self._stream.write(payload)
            self._stream.flush()

    def _worker_loop(self):
        pending = []
        while not self._stop_event.is_set() or (self._queue is not None and not self._queue.empty()):
            try:
                record = self._queue.get(timeout=self._flush_interval)
                pending.append(record)
                while True:
                    try:
                        pending.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                pass
            if pending:
                self._write_batch(pending)
                pending.clear()

    @staticmethod
    def _materialize(value):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, BaseException):
            return str(value)
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return value

    @staticmethod
    def _json_default(value):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, BaseException):
            return str(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return str(value)
```

#### (M)ui_logger.py

```python
import logging

from python_tty.runtime.events import UIEventLevel
from python_tty.runtime.router import proxy_print


class ConsoleHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            log = self.format(record)
            proxy_print(log, UIEventLevel.DEBUG, source="tty")
        except Exception:
            self.handleError(record)
```



### config

#### (M)__init\_\_.py

```python
from python_tty.config.config import (
    AuditConfig,
    Config,
    ConsoleFactoryConfig,
    ConsoleManagerConfig,
    ExecutorConfig,
)

__all__ = [
    "Config",
    "AuditConfig",
    "ConsoleFactoryConfig",
    "ConsoleManagerConfig",
    "ExecutorConfig",
]
```

#### (M)config.py

```python
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, TextIO, Tuple, Type

if TYPE_CHECKING:
    from python_tty.audit.sink import AuditSink
    from python_tty.runtime.router import OutputRouter


@dataclass
class AuditConfig:
    """Audit sink configuration.

    Attributes:
        enabled: Toggle audit recording.
        file_path: File path to append JSONL audit records.
        stream: File-like stream to write audit records.
        async_mode: Enable async background writer when stream is set.
        flush_interval: Flush interval (seconds) for async writer.
        keep_in_memory: Keep records in memory buffer for testing.
        sink: Custom AuditSink instance to use instead of file/stream.
    """
    enabled: bool = False
    file_path: Optional[str] = None
    stream: Optional[TextIO] = None
    async_mode: bool = False
    flush_interval: float = 1.0
    keep_in_memory: bool = False
    sink: Optional["AuditSink"] = None


@dataclass
class ExecutorConfig:
    """Executor runtime configuration.

    Attributes:
        workers: Number of worker tasks to consume invocations.
        retain_last_n: Keep only the last N completed runs in memory.
        ttl_seconds: Time-to-live for completed runs.
        pop_on_wait: Drop run state after wait_result completion.
        exempt_exceptions: Exceptions treated as cancellations.
        emit_run_events: Emit start/success/failure RuntimeEvent state.
        event_history_max: Max events kept per run for history replay.
        event_history_ttl: Time-to-live for per-run event history.
        audit: Audit sink configuration.
    """
    workers: int = 1
    retain_last_n: Optional[int] = None
    ttl_seconds: Optional[float] = None
    pop_on_wait: bool = False
    exempt_exceptions: Optional[Tuple[Type[BaseException], ...]] = None
    emit_run_events: bool = True
    event_history_max: Optional[int] = 1000
    event_history_ttl: Optional[float] = 3600.0
    audit: AuditConfig = field(default_factory=AuditConfig)


@dataclass
class ConsoleManagerConfig:
    """Console manager configuration.

    Attributes:
        use_patch_stdout: Patch stdout for prompt_toolkit rendering.
        output_router: Output router instance for UI events.
    """
    use_patch_stdout: bool = True
    output_router: Optional["OutputRouter"] = None


@dataclass
class ConsoleFactoryConfig:
    """Console factory bootstrap configuration.

    Attributes:
        run_mode: "tty" for single-thread TTY mode, "concurrent" for
            main-thread asyncio loop with TTY in a background thread.
        start_executor: Auto-start the executor when the factory starts.
        executor_in_thread: Start executor in a background thread (tty mode).
        executor_thread_name: Thread name for the executor loop thread.
        tty_thread_name: Thread name for the TTY loop (concurrent mode).
        shutdown_executor: Shutdown executor when the factory stops.
    """
    run_mode: str = "tty"
    start_executor: bool = True
    executor_in_thread: bool = True
    executor_thread_name: str = "ExecutorLoop"
    tty_thread_name: str = "TTYLoop"
    shutdown_executor: bool = True


@dataclass
class Config:
    """Top-level configuration for python-tty."""
    console_manager: ConsoleManagerConfig = field(default_factory=ConsoleManagerConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    console_factory: ConsoleFactoryConfig = field(default_factory=ConsoleFactoryConfig)
```

### commands

#### (M)__init\_\_.py

```python
from python_tty.commands.core import BaseCommands, CommandValidator
from python_tty.commands.registry import (
    ArgSpec,
    CommandDef,
    CommandInfo,
    CommandRegistry,
    CommandStyle,
    COMMAND_REGISTRY,
    define_command_style,
)

__all__ = [
    "ArgSpec",
    "BaseCommands",
    "CommandDef",
    "CommandInfo",
    "CommandRegistry",
    "CommandStyle",
    "COMMAND_REGISTRY",
    "CommandValidator",
    "define_command_style",
]
```

#### core.py

```python
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError

from python_tty.commands.registry import COMMAND_REGISTRY, ArgSpec
from python_tty.exceptions.console_exception import ConsoleInitException
from python_tty.utils import split_cmd


class CommandValidator(Validator):
    def __init__(self, command_validators: dict, enable_undefined_command=False):
        self.command_validators = command_validators
        self.enable_undefined_command = enable_undefined_command
        super().__init__()

    def validate(self, document: Document) -> None:
        try:
            token, arg_text, _ = split_cmd(document.text)
            if token in self.command_validators.keys():
                cmd_validator = self.command_validators[token]
                cmd_validator.validate(Document(text=arg_text))
            else:
                if not self.enable_undefined_command:
                    raise ValidationError(message="Bad command")
        except ValueError:
            return


class BaseCommands:
    def __init__(self, console, registry=None):
        self.console = console
        self.registry = registry if registry is not None else COMMAND_REGISTRY
        self.command_defs = []
        self.command_defs_by_name = {}
        self.command_defs_by_id = {}
        self.command_completers = {}
        self.command_validators = {}
        self.command_funcs = {}
        self._init_funcs()
        self.completer = NestedCompleter.from_nested_dict(self.command_completers)
        self.validator = CommandValidator(self.command_validators, self.enable_undefined_command)

    @property
    def enable_undefined_command(self):
        return False

    def _init_funcs(self):
        if self.console is None:
            raise ConsoleInitException("Console is None")
        defs = self.registry.get_command_defs_for_console(self.console.__class__)
        if len(defs) == 0:
            defs = self.registry.collect_from_commands_cls(self.__class__)
        self.command_defs = defs
        self._collect_completer_and_validator(defs)

    def _collect_completer_and_validator(self, defs):
        for command_def in defs:
            self._map_components(command_def)

    def _map_components(self, command_def):
        command_id = self._build_command_id(command_def)
        if command_id is not None:
            self.command_defs_by_id[command_id] = command_def
        for command_name in command_def.all_names():
            self.command_funcs[command_name] = command_def.func
            self.command_defs_by_name[command_name] = command_def
            if command_def.completer is None:
                self.command_completers[command_name] = None
            else:
                self.command_completers[command_name] = self._build_completer(command_def)
            self.command_validators[command_name] = self._build_validator(command_def)

    def _build_completer(self, command_def):
        try:
            return command_def.completer(self.console, command_def.arg_spec)
        except TypeError:
            try:
                return command_def.completer(self.console)
            except TypeError as exc:
                raise ConsoleInitException(
                    "Completer init failed. Use completer_from(...) to adapt "
                    "prompt_toolkit completers."
                ) from exc

    def _build_validator(self, command_def):
        if command_def.validator is None:
            return DummyValidator()
        try:
            return command_def.validator(self.console, command_def.func, command_def.arg_spec)
        except TypeError:
            return command_def.validator(self.console, command_def.func)

    def get_command_def(self, command_name):
        command_def = self.command_defs_by_id.get(command_name)
        if command_def is not None:
            return command_def
        return self.command_defs_by_name.get(command_name)

    def get_command_def_by_id(self, command_id):
        return self.command_defs_by_id.get(command_id)

    def get_command_id(self, command_name):
        command_def = self.command_defs_by_name.get(command_name)
        if command_def is None:
            return None
        return self._build_command_id(command_def)

    def _build_command_id(self, command_def):
        console_name = getattr(self.console, "console_name", None)
        if not console_name:
            console_name = self.console.__class__.__name__.lower()
        return f"cmd:{console_name}:{command_def.func_name}"

    def deserialize_args(self, command_def, raw_text):
        if command_def.arg_spec is None:
            arg_spec = ArgSpec.from_signature(command_def.func)
            return arg_spec.parse(raw_text)
        return command_def.arg_spec.parse(raw_text)
```

#### decorators.py

```python
from functools import wraps

from prompt_toolkit.completion import Completer
from prompt_toolkit.validation import Validator

from python_tty.commands import BaseCommands
from python_tty.commands.registry import COMMAND_REGISTRY, CommandInfo, CommandStyle, define_command_style
from python_tty.exceptions.console_exception import ConsoleInitException


def commands(commands_cls):
    """Bind a BaseCommands subclass to a Console class for auto command wiring."""
    if not issubclass(commands_cls, BaseCommands):
        raise ConsoleInitException("Commands must inherit BaseCommands")

    def decorator(console_cls):
        from python_tty.consoles import MainConsole, SubConsole
        if not issubclass(console_cls, (MainConsole, SubConsole)):
            raise ConsoleInitException("commands decorator must target a Console class")
        existing = getattr(console_cls, "__commands_cls__", None)
        if existing is not None and existing is not commands_cls:
            raise ConsoleInitException(
                f"{console_cls.__name__} already binds to {existing.__name__}; "
                f"cannot bind to {commands_cls.__name__} again"
            )
        setattr(console_cls, "__commands_cls__", commands_cls)
        COMMAND_REGISTRY.register_console_commands(console_cls, commands_cls)
        return console_cls

    return decorator


def register_command(command_name: str, command_description: str, command_alias=None,
                     command_style=CommandStyle.LOWERCASE,
                     completer=None, validator=None, arg_spec=None):
    """Declare command metadata for a command method on a BaseCommands subclass."""
    if completer is not None and not isinstance(completer, type):
        raise ConsoleInitException("Command completer must be a class")
    if validator is not None and not isinstance(validator, type):
        raise ConsoleInitException("Command validator must be a class")
    if completer is not None and not issubclass(completer, Completer):
        raise ConsoleInitException("Command completer must inherit Completer")
    if validator is not None and not issubclass(validator, Validator):
        raise ConsoleInitException("Command validator must inherit Validator")
    def inner_wrapper(func):
        func.info = CommandInfo(define_command_style(command_name, command_style), command_description,
                                completer, validator, command_alias, arg_spec)
        func.type = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            return result

        return wrapper

    return inner_wrapper
```

#### registry.py

```python
import re
import enum
import inspect

from prompt_toolkit.completion import Completer
from prompt_toolkit.validation import ValidationError, Validator
from python_tty.exceptions.console_exception import ConsoleInitException
from python_tty.utils.tokenize import tokenize_cmd



def define_command_style(command_name, style):
    if style == CommandStyle.NONE:
        return command_name
    elif style == CommandStyle.LOWERCASE:
        return command_name.lower()
    elif style == CommandStyle.UPPERCASE:
        return command_name.upper()
    command_name = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', command_name)
    command_name = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', command_name)
    if style == CommandStyle.POWERSHELL:
        return command_name
    elif style == CommandStyle.SLUGIFIED:
        return command_name.lower()


class CommandStyle(enum.Enum):
    NONE = 0  # ClassName => ClassName
    LOWERCASE = 1  # ClassName => classname
    UPPERCASE = 2  # ClassName => CLASSNAME
    POWERSHELL = 3  # ClassName => Class-Name
    SLUGIFIED = 4  # ClassName => class-name


class ArgSpec:
    def __init__(self, min_args=0, max_args=0, variadic=False):
        self.min_args = min_args
        self.max_args = max_args
        self.variadic = variadic

    @classmethod
    def from_signature(cls, func, skip_first=True):
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if skip_first and params:
            params = params[1:]
        min_args = 0
        max_args = 0
        variadic = False
        for param in params:
            if param.kind == param.VAR_POSITIONAL:
                variadic = True
                continue
            if param.default is param.empty:
                min_args += 1
            max_args += 1
        if variadic:
            max_args = None
        return cls(min_args, max_args, variadic)

    def parse(self, text):
        tokens = tokenize_cmd(text)
        return tokens

    def count_args(self, text):
        tokens = tokenize_cmd(text)
        return len(tokens)

    def validate_count(self, count):
        if count < self.min_args:
            raise ValidationError(message="Not enough parameters set!")
        if self.max_args is not None and count > self.max_args:
            raise ValidationError(message="Too many parameters set!")


class CommandInfo:
    def __init__(self, func_name, func_description,
                 completer=None, validator=None,
                 command_alias=None, arg_spec=None):
        self.func_name = func_name
        self.func_description = func_description
        self.completer = completer
        self.validator = validator
        self.arg_spec = arg_spec
        if command_alias is None:
            self.alias = []
        else:
            if type(command_alias) == str:
                self.alias = [command_alias]
            elif type(command_alias) == list:
                self.alias = command_alias
            else:
                self.alias = []


class CommandDef:
    def __init__(self, func_name, func, func_description,
                 command_alias=None, completer=None, validator=None,
                 arg_spec=None):
        self.func_name = func_name
        self.func = func
        self.func_description = func_description
        self.completer = completer
        self.validator = validator
        self.arg_spec = arg_spec
        if command_alias is None:
            self.alias = []
        else:
            self.alias = command_alias

    def all_names(self):
        return [self.func_name] + list(self.alias)


class CommandRegistry:
    def __init__(self):
        self._console_command_classes = {}
        self._commands_defs = {}
        self._console_defs = {}

    def register_console_commands(self, console_cls, commands_cls):
        self._console_command_classes[console_cls] = commands_cls

    def get_commands_cls(self, console_cls):
        return self._console_command_classes.get(console_cls)

    def register(self, func, console_cls=None, commands_cls=None,
                 command_name=None, command_description="", command_alias=None,
                 command_style=CommandStyle.LOWERCASE,
                 completer=None, validator=None, arg_spec=None):
        if completer is not None and not isinstance(completer, type):
            raise ConsoleInitException("Command completer must be a class")
        if validator is not None and not isinstance(validator, type):
            raise ConsoleInitException("Command validator must be a class")
        if completer is not None and not issubclass(completer, Completer):
            raise ConsoleInitException("Command completer must inherit Completer")
        if validator is not None and not issubclass(validator, Validator):
            raise ConsoleInitException("Command validator must inherit Validator")
        if command_name is None:
            command_name = func.__name__
        info = CommandInfo(define_command_style(command_name, command_style),
                           command_description, completer, validator,
                           command_alias, arg_spec)
        func.info = info
        func.type = None
        command_def = CommandDef(info.func_name, func, info.func_description,
                                 info.alias, info.completer, info.validator,
                                 info.arg_spec)
        if commands_cls is not None:
            self._commands_defs.setdefault(commands_cls, []).append(command_def)
        if console_cls is not None:
            self._console_defs.setdefault(console_cls, []).append(command_def)
        return command_def

    def collect_from_commands_cls(self, commands_cls):
        if commands_cls in self._commands_defs:
            return self._commands_defs[commands_cls]
        defs = []
        for member_name in dir(commands_cls):
            if member_name.startswith("_"):
                continue
            member = getattr(commands_cls, member_name)
            if (inspect.ismethod(member) or inspect.isfunction(member)) and hasattr(member, "info"):
                command_info = member.info
                arg_spec = command_info.arg_spec or ArgSpec.from_signature(member)
                defs.append(CommandDef(command_info.func_name, member,
                                       command_info.func_description,
                                       command_info.alias,
                                       command_info.completer,
                                       command_info.validator,
                                       arg_spec))
        self._commands_defs[commands_cls] = defs
        return defs

    def get_command_defs_for_console(self, console_cls):
        defs = []
        commands_cls = self.get_commands_cls(console_cls)
        if commands_cls is not None:
            defs.extend(self.collect_from_commands_cls(commands_cls))
        defs.extend(self._console_defs.get(console_cls, []))
        return defs


COMMAND_REGISTRY = CommandRegistry()
```

#### general.py

```python
from abc import ABC, abstractmethod

from prompt_toolkit.completion import Completer, WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

from python_tty.commands.registry import ArgSpec


class GeneralValidator(Validator):
    """Default validator that checks argument count and allows custom validation."""
    def __init__(self, console, func, arg_spec=None):
        self.console = console
        self.func = func
        self.arg_spec = arg_spec or ArgSpec.from_signature(func)
        super().__init__()

    def validate(self, document: Document) -> None:
        try:
            args = self.arg_spec.parse(document.text)
            self.arg_spec.validate_count(len(args))
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValidationError(message=str(exc)) from exc
        try:
            self.custom_validate(args, document.text)
        except TypeError:
            self.custom_validate(document.text)

    def custom_validate(self, args, text: str):
        pass


def _allow_complete_for_spec(arg_spec, text, args):
    if arg_spec.max_args is None:
        return True
    if text != "" and text[-1].isspace():
        return len(args) < arg_spec.max_args
    return len(args) <= arg_spec.max_args


class GeneralCompleter(Completer, ABC):
    """Base completer with ArgSpec-aware completion and console injection."""
    def __init__(self, console, arg_spec=None, ignore_case=True):
        self.console = console
        self.arg_spec = arg_spec or ArgSpec()
        self.ignore_case = ignore_case
        super().__init__()

    @abstractmethod
    def get_candidates(self, args, text: str):
        pass

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        try:
            args = self.arg_spec.parse(text)
        except ValueError:
            return
        if not _allow_complete_for_spec(self.arg_spec, text, args):
            return
        words = self.get_candidates(args, text)
        if not words:
            return
        completer = WordCompleter(words, ignore_case=self.ignore_case)
        yield from completer.get_completions(document, complete_event)

    def _allow_complete(self, text, args):
        return _allow_complete_for_spec(self.arg_spec, text, args)


class PromptToolkitCompleterAdapter(Completer):
    completer_cls = None
    completer_kwargs = {}

    def __init__(self, console, arg_spec=None):
        self.console = console
        self.arg_spec = arg_spec or ArgSpec()
        if self.completer_cls is None:
            raise ValueError("completer_cls must be set for adapter")
        self._inner = self.completer_cls(**self.get_completer_kwargs())
        super().__init__()

    def get_completer_kwargs(self):
        return dict(self.completer_kwargs)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        try:
            args = self.arg_spec.parse(text)
        except ValueError:
            return
        if not _allow_complete_for_spec(self.arg_spec, text, args):
            return
        yield from self._inner.get_completions(document, complete_event)


def completer_from(completer_cls, **kwargs):
    """Build a completer adapter class for a prompt_toolkit completer."""
    class _Adapter(PromptToolkitCompleterAdapter):
        pass

    _Adapter.completer_cls = completer_cls
    _Adapter.completer_kwargs = kwargs
    return _Adapter
```

#### mixins.py

```python
import inspect

from python_tty.runtime.router import proxy_print
from python_tty.commands import BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.commands.general import GeneralValidator
from python_tty.exceptions.console_exception import ConsoleExit, SubConsoleExit
from python_tty.utils.table import Table


class CommandMixin:
    pass


class BackMixin(CommandMixin):
    @register_command("back", "Back to forward tty", validator=GeneralValidator)
    def run_back(self):
        raise SubConsoleExit


class QuitMixin(CommandMixin):
    @register_command("quit", "Quit Console", ["exit", "q"], validator=GeneralValidator)
    def run_quit(self):
        raise ConsoleExit


class HelpMixin(CommandMixin):
    @register_command("help", "Display help information", ["?"], validator=GeneralValidator)
    def run_help(self):
        header = ["Command", "Description"]
        base_funcs = []
        custom_funcs = []
        base_commands_funcs = []
        for cls in self.__class__.mro():
            if cls is CommandMixin:
                continue
            if issubclass(cls, CommandMixin) and not issubclass(cls, BaseCommands):
                base_commands_funcs.extend([member[1] for member in inspect.getmembers(cls, inspect.isfunction)])
        for name, func in self.command_funcs.items():
            row = [name, func.info.func_description]
            if func in base_commands_funcs:
                base_funcs.append(row)
            else:
                custom_funcs.append(row)
        if base_funcs:
            proxy_print(Table(header, base_funcs, "Core Commands"), source="tty")
        if custom_funcs:
            proxy_print(Table(header, custom_funcs, "Custom Commands"), source="tty")

class DefaultCommands(BaseCommands, HelpMixin, QuitMixin):
    pass
```

#### (P)exmaple

##### (M)__init\_\_.py

```python
from src.commands.examples.root_commands import RootCommands
from src.commands.examples.sub_commands import SubCommands

__all__ = [
    "RootCommands",
    "SubCommands",
]
```

##### (M)root_commands.py

```python
from python_tty.commands import BaseCommands
from python_tty.commands.decorators import register_command
from python_tty.commands.general import GeneralValidator
from python_tty.commands.mixins import HelpMixin, QuitMixin
from python_tty.runtime.events import UIEventLevel
from python_tty.runtime.router import proxy_print


class RootCommands(BaseCommands, HelpMixin, QuitMixin):
    @property
    def enable_undefined_command(self):
        return True
    
    @register_command("use", "Enter sub console", validator=GeneralValidator)
    def run_use(self, console_name):
        manager = getattr(self.console, "manager", None)
        if manager is None:
            proxy_print("Console manager not configured", UIEventLevel.WARNING)
            return
        if not manager.is_registered(console_name):
            proxy_print(f"Console [{console_name}] not registered", UIEventLevel.ERROR)
            return
        manager.push(console_name)

    @register_command("debug", "Debug root console, display some information", validator=GeneralValidator)
    def run_debug(self, *args):
        framework = self.console.service
        proxy_print(str(framework))


if __name__ == '__main__':
    pass
```

##### (M)sub_commands.py

```python
from src.commands import BaseCommands
from src.commands.decorators import register_command
from src.commands.general import GeneralValidator
from src.commands.mixins import BackMixin, HelpMixin, QuitMixin


class SubCommands(BaseCommands, HelpMixin, QuitMixin, BackMixin):
    @register_command("debug", "Debug command, display some information", [], validator=GeneralValidator)
    def run_debug(self):
        pass
```

### consoles

#### (M)__init\_\_.py

```python
from python_tty.consoles.core import BaseConsole, MainConsole, SubConsole
from python_tty.consoles.decorators import root, sub, multi
from python_tty.consoles.registry import REGISTRY
from python_tty.consoles.loader import DEFAULT_CONSOLE_MODULES

__all__ = [
    "BaseConsole",
    "MainConsole",
    "SubConsole",
    "DEFAULT_CONSOLE_MODULES",
    "REGISTRY",
    "root",
    "sub",
    "multi",
]
```

#### core.py

```python
import uuid
from abc import ABC

from prompt_toolkit import PromptSession

from python_tty.runtime.events import UIEventListener, UIEventSpeaker
from python_tty.executor import Invocation
from python_tty.executor.execution import ExecutionBinding, ExecutionContext
from python_tty.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from python_tty.runtime.router import proxy_print
from python_tty.utils import split_cmd


class BaseConsole(ABC, UIEventListener):
    forward_console = None

    def __init__(self, console_message, console_style, parent=None, manager=None):
        self.uid = str(uuid.uuid4())
        self.parent = parent
        self.manager = manager if manager is not None else getattr(parent, "manager", None)
        if self.manager is not None:
            self.service = self.manager.service
        else:
            self.service = getattr(parent, "service", None)
        BaseConsole.forward_console = self
        self.commands = self._build_commands()
        self.session = PromptSession(console_message, style=console_style,
                                     completer=self.commands.completer,
                                     validator=self.commands.validator)
        if isinstance(self.service, UIEventSpeaker):
            self.service.add_event_listener(self)

    def init_commands(self):
        return None

    def _build_commands(self):
        from python_tty.commands import COMMAND_REGISTRY
        commands_cls = getattr(self.__class__, "__commands_cls__", None)
        if commands_cls is None:
            commands = self.init_commands()
            if commands is not None:
                return commands
            commands_cls = COMMAND_REGISTRY.get_commands_cls(self.__class__)
        if commands_cls is None:
            from python_tty.commands.mixins import DefaultCommands
            commands_cls = DefaultCommands
        return commands_cls(self)

    def handler_event(self, event):
        if BaseConsole.forward_console is not None and BaseConsole.forward_console == self:
            proxy_print(event.msg, event.level, source=event.source or "tty")

    def run(self, invocation: Invocation):
        command_def = self.commands.get_command_def_by_id(invocation.command_id)
        if command_def is None and invocation.command_name is not None:
            command_def = self.commands.get_command_def(invocation.command_name)
        if command_def is None:
            raise ValueError(f"Command not found: {invocation.command_id}")
        if len(invocation.argv) == 0:
            return command_def.func(self.commands)
        return command_def.func(self.commands, *invocation.argv)

    def execute(self, cmd):
        try:
            ctx, token = self._build_context(cmd)
            if ctx is None:
                if token != "":
                    self.cmd_invoke_miss(cmd)
                return
            invocation = ctx.to_invocation()
            executor = getattr(self.manager, "executor", None) if self.manager is not None else None
            if executor is None:
                binding = ExecutionBinding(service=self.service, manager=self.manager, ctx=ctx, console=self)
                binding.execute(invocation)
                return
            binding = ExecutionBinding(service=self.service, manager=self.manager, ctx=ctx, console=self)
            handler = lambda inv: binding.execute(inv)
            run_id = executor.submit_threadsafe(invocation, handler=handler)
            executor.wait_result_sync(run_id)
        except ValueError:
            return

    def _build_context(self, cmd):
        token, arg_text, _ = split_cmd(cmd)
        if token == "":
            return None, token
        command_def = self.commands.get_command_def(token)
        if command_def is None:
            return None, token
        param_list = self.commands.deserialize_args(command_def, arg_text)
        command_id = self.commands.get_command_id(token)
        console_name = getattr(self, "console_name", None)
        if not console_name:
            console_name = self.__class__.__name__.lower()
        ctx = ExecutionContext(
            source="tty",
            principal=None,
            console_name=console_name,
            command_name=token,
            command_id=command_id,
            argv=param_list,
            raw_cmd=cmd,
        )
        return ctx, token

    def cmd_invoke_miss(self, cmd: str):
        pass

    def clean_console(self):
        if isinstance(self.service, UIEventSpeaker):
            self.service.remove_event_listener(self)
        if BaseConsole.forward_console == self:
            BaseConsole.forward_console = self.parent

    def start(self):
        if self.manager is not None:
            self.manager.run_with(self)
            return
        while True:
            try:
                cmd = self.session.prompt()
                self.execute(cmd)
            except ConsoleExit:
                if self.parent is None:
                    break
                else:
                    raise ConsoleExit
            except SubConsoleExit:
                break
            except (KeyboardInterrupt, ValueError):
                # FIXME: Careful deal this!
                # continue
                break
        self.clean_console()


class MainConsole(BaseConsole):
    def __init__(self, console_message, console_style, parent=None, manager=None):
        if parent is not None:
            raise ConsoleInitException("MainConsole parent must be None")
        super().__init__(console_message, console_style, parent=None, manager=manager)


class SubConsole(BaseConsole):
    def __init__(self, console_message, console_style, parent=None, manager=None):
        if parent is None:
            raise ConsoleInitException("SubConsole parent is None")
        super().__init__(console_message, console_style, parent=parent, manager=manager)
```

#### decorators.py

```python
from python_tty.consoles.registry import REGISTRY
from python_tty.exceptions.console_exception import ConsoleInitException


def root(console_cls):
    """Mark a MainConsole subclass as the single root console."""
    from python_tty.consoles import MainConsole
    if not issubclass(console_cls, MainConsole):
        raise ConsoleInitException("Root console must inherit MainConsole")
    REGISTRY.set_root(console_cls)
    return console_cls


def sub(parent_name):
    """Register a SubConsole subclass to a single parent console by name."""
    if not isinstance(parent_name, str) or parent_name == "":
        raise ConsoleInitException("Sub console parent name is empty")

    def decorator(console_cls):
        from python_tty.consoles import SubConsole
        if not issubclass(console_cls, SubConsole):
            raise ConsoleInitException("Sub console must inherit SubConsole")
        REGISTRY.add_sub(console_cls, parent_name)
        return console_cls

    return decorator


def multi(parent_map):
    """Register a reusable SubConsole for multiple parents with instance names."""
    if not isinstance(parent_map, dict) or len(parent_map) <= 0:
        raise ConsoleInitException("Multi console mapping is empty")

    def decorator(console_cls):
        from python_tty.consoles import SubConsole
        if not issubclass(console_cls, SubConsole):
            raise ConsoleInitException("Multi console must inherit SubConsole")
        REGISTRY.add_multi(console_cls, parent_map)
        return console_cls

    return decorator
```

#### registry.py

```python
from python_tty.exceptions.console_exception import ConsoleInitException


def _get_console_name(console_cls):
    name = getattr(console_cls, "console_name", None)
    if name:
        return name
    name = getattr(console_cls, "CONSOLE_NAME", None)
    if name:
        return name
    return console_cls.__name__.lower()


def _get_console_kwargs(console_cls):
    kwargs = getattr(console_cls, "console_kwargs", None)
    if kwargs is None:
        return {}
    if not isinstance(kwargs, dict):
        raise ConsoleInitException("console_kwargs must be dict")
    return kwargs


class SubConsoleEntry:
    def __init__(self, console_cls, parent_name, name):
        self.console_cls = console_cls
        self.parent_name = parent_name
        self.name = name


class ConsoleRegistry:
    def __init__(self):
        self._root_cls = None
        self._root_name = None
        self._subs = {}

    def set_root(self, console_cls):
        if self._root_cls is not None:
            raise ConsoleInitException("Root console already set")
        self._root_cls = console_cls
        self._root_name = _get_console_name(console_cls)

    def add_sub(self, console_cls, parent_name):
        name = _get_console_name(console_cls)
        if name == self._root_name or name in self._subs:
            raise ConsoleInitException(f"Console name duplicate [{name}]")
        self._subs[name] = SubConsoleEntry(console_cls, parent_name, name)

    def add_multi(self, console_cls, parent_map):
        if not isinstance(parent_map, dict) or len(parent_map) <= 0:
            raise ConsoleInitException("Multi console mapping is empty")
        for parent_name, instance_name in parent_map.items():
            if not isinstance(parent_name, str) or parent_name == "":
                raise ConsoleInitException("Multi console parent name is empty")
            if not isinstance(instance_name, str) or instance_name == "":
                raise ConsoleInitException("Multi console instance name is empty")
            resolved_name = _resolve_instance_name(parent_name, instance_name)
            if resolved_name == self._root_name or resolved_name in self._subs:
                raise ConsoleInitException(f"Console name duplicate [{resolved_name}]")
            self._subs[resolved_name] = SubConsoleEntry(console_cls, parent_name, resolved_name)

    def get_root(self):
        if self._root_cls is None:
            return None, None
        root_name = self._root_name or _get_console_name(self._root_cls)
        return self._root_cls, root_name

    def get_subs(self):
        return dict(self._subs)

    def iter_consoles(self):
        root_cls, root_name = self.get_root()
        if root_cls is not None and root_name is not None:
            yield root_name, root_cls, None
        for name, entry in self._subs.items():
            yield name, entry.console_cls, entry.parent_name

    def get_console_tree(self):
        _, root_name = self.get_root()
        if not root_name:
            return None
        return _build_console_tree(root_name, self._subs)

    def get_console_map(self):
        console_map = {}
        for name, console_cls, parent in self.iter_consoles():
            console_map[name] = {
                "name": name,
                "parent": parent,
                "type": console_cls.__name__,
                "module": console_cls.__module__,
            }
        return console_map

    def register_all(self, manager):
        if self._root_cls is None:
            raise ConsoleInitException("Root console not set")
        manager.set_root_name(self._root_name)
        manager.register(self._root_name, self._root_cls, **_get_console_kwargs(self._root_cls))
        for name, entry in self._subs.items():
            manager.register(name, entry.console_cls, **_get_console_kwargs(entry.console_cls))
        for name, entry in self._subs.items():
            if not manager.is_registered(entry.parent_name):
                raise ConsoleInitException(
                    f"Parent console [{entry.parent_name}] for [{name}] not registered"
                )
        console_tree = _build_console_tree(self._root_name, self._subs)
        manager.set_console_tree(console_tree)


def _resolve_instance_name(parent_name, instance_name):
    prefix = f"{parent_name}_"
    if instance_name.startswith(prefix):
        return instance_name
    return f"{prefix}{instance_name}"


def _build_console_tree(root_name, sub_entries):
    children_map = {}
    for name, entry in sub_entries.items():
        children_map.setdefault(entry.parent_name, []).append(name)
    for _, children in children_map.items():
        children.sort()
    all_names = [root_name]
    all_names.extend(list(sub_entries.keys()))
    for name in all_names:
        if name not in children_map:
            children_map[name] = []
    return {
        "root": root_name,
        "children": children_map,
    }


REGISTRY = ConsoleRegistry()
```

#### loader.py

```python
import importlib


DEFAULT_CONSOLE_MODULES = ()


def load_consoles(modules=None):
    """Import console modules so class decorators can register themselves."""
    if modules is None:
        modules = DEFAULT_CONSOLE_MODULES
    elif not isinstance(modules, (list, tuple)):
        modules = [modules]
    for module in modules:
        importlib.import_module(module)
```

#### manager.py

```python
from prompt_toolkit.patch_stdout import patch_stdout

from python_tty.config import ConsoleManagerConfig
from python_tty.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from python_tty.runtime.events import UIEventLevel, UIEventSpeaker
from python_tty.runtime.provider import get_router
from python_tty.runtime.router import proxy_print


class ConsoleEntry:
    def __init__(self, console_cls, kwargs):
        self.console_cls = console_cls
        self.kwargs = kwargs


class ConsoleManager:
    def __init__(self, service=None, executor=None, on_shutdown=None, config: ConsoleManagerConfig = None):
        self._registry = {}
        self._stack = []
        self._console_tree = None
        self._root_name = None
        self._service = service
        self._executor = executor
        self._on_shutdown = on_shutdown
        self._shutdown_called = False
        self._config = config if config is not None else ConsoleManagerConfig()
        self._output_router = self._config.output_router or get_router()
        self._use_patch_stdout = self._config.use_patch_stdout
        self._warn_service_if_needed(service)

    def register(self, name, console_cls, **kwargs):
        self._registry[name] = ConsoleEntry(console_cls, kwargs)

    def is_registered(self, name):
        return name in self._registry

    def set_root_name(self, root_name):
        self._root_name = root_name

    def set_console_tree(self, console_tree):
        self._console_tree = console_tree

    @property
    def console_tree(self):
        return self._console_tree

    @property
    def service(self):
        return self._service

    @property
    def executor(self):
        return self._executor

    def clean(self):
        if self._shutdown_called:
            return
        self._shutdown_called = True
        if self._output_router is not None:
            self._output_router.clear_session()
        if callable(self._on_shutdown):
            self._on_shutdown()

    def _warn_service_if_needed(self, service):
        if service is not None and not isinstance(service, UIEventSpeaker):
            msg = f"The Service core[{service.__class__}] doesn't extend the [UIEventSpeaker],"\
                  " which may affect the output of the Service core on the UI!"
            proxy_print(msg, UIEventLevel.WARNING, source="tty")

    @property
    def current(self):
        return self._stack[-1] if self._stack else None

    def push(self, name, **kwargs):
        if name not in self._registry:
            raise KeyError(f"Console [{name}] not registered")
        entry = self._registry[name]
        init_kwargs = dict(entry.kwargs)
        init_kwargs.update(kwargs)
        parent = self.current
        console = entry.console_cls(parent=parent, manager=self, **init_kwargs)
        console.console_name = name
        self._stack.append(console)
        self._bind_output_router()
        return console

    def pop(self):
        if not self._stack:
            return None
        console = self._stack.pop()
        console.clean_console()
        self._bind_output_router()
        return self.current

    def run(self, root_name=None, **kwargs):
        if root_name is None:
            root_name = self._root_name
        if root_name is None:
            raise ConsoleInitException("Root console not registered")
        self.push(root_name, **kwargs)
        self._loop()

    def run_with(self, root_console):
        if root_console.parent is not None:
            raise ConsoleInitException("Root console parent must be None")
        root_console.manager = self
        if getattr(root_console, "console_name", None) is None:
            root_console.console_name = root_console.__class__.__name__.lower()
        self._stack.append(root_console)
        self._bind_output_router()
        self._loop()

    def _loop(self):
        try:
            while self._stack:
                try:
                    self._bind_output_router()
                    cmd = self._prompt()
                    self.current.execute(cmd)
                except SubConsoleExit:
                    self.pop()
                except ConsoleExit:
                    while self._stack:
                        self.pop()
                    break
                except (KeyboardInterrupt, ValueError):
                    while self._stack:
                        self.pop()
                    break
        finally:
            self.clean()

    def _prompt(self):
        if self._use_patch_stdout:
            with patch_stdout():
                return self.current.session.prompt()
        return self.current.session.prompt()

    def _bind_output_router(self):
        if self._output_router is None:
            return
        current = self.current
        if current is None:
            self._output_router.clear_session()
            return
        self._output_router.bind_session(current.session)
```

#### (P)exmaple

##### (M)__init\_\_.py

```python
from src.consoles.examples.root_console import RootConsole
from src.consoles.examples.sub_console import ModuleConsole

__all__ = [
    "RootConsole",
    "ModuleConsole",
]
```

##### (M)root_console.py

```python
from prompt_toolkit.styles import Style

from src.commands.decorators import commands
from src.commands.examples.root_commands import RootCommands
from src.consoles import MainConsole, root

message = [
    ('class:host', 'vef1'),
    ('class:prompt', ' '),
    ('class:symbol', '>'),
    ('class:prompt', ' ')
]
style = Style.from_dict({
    # User input(default text)
    '': '',
    'host': '#00aa00 underline',
    'symbol': '#00ffff'
})


@root
@commands(RootCommands)
class RootConsole(MainConsole):
    console_name = "root"

    def __init__(self, parent=None, manager=None):
        super().__init__(message, style, parent=parent, manager=manager)

    def cmd_invoke_miss(self, cmd: str):
        print(f"Invoke os shell command [{cmd}]")

    def clean_console(self):
        super().clean_console()
```

##### (M)sub_console.py

```python
from prompt_toolkit.styles import Style

from src.commands.decorators import commands
from src.commands.examples.sub_commands import SubCommands
from src.consoles import SubConsole, sub


style = Style.from_dict({
    # User input(default text)
    '': '',
    'host': '#00aaaa',
    'symbol': '#00ffaa'
})


@sub("root")
@commands(SubCommands)
class ModuleConsole(SubConsole):
    console_name = "module"

    def __init__(self, module_name=None, parent=None, manager=None):
        if module_name is None:
            module_name = self.console_name
        message = [
            ('class:host', module_name),
            ('class:prompt', ' '),
            ('class:symbol', '>'),
            ('class:prompt', ' ')
        ]
        super().__init__(message, style, parent=parent, manager=manager)

    def clean_console(self):
        super().clean_console()
```



### exceptions

#### (M)__init\_\_.py

```python
class UIBaseException(Exception):
    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    def __str__(self):
        return self.msg
```

#### (M)console_exception.py

```python
class ConsoleInitException(Exception):
    """ Console init exception """
    def __init__(self, message: str):
        super().__init__(message)


class ConsoleExit(Exception):
    pass


class SubConsoleExit(Exception):
    pass

```

### executor

#### (M)__init\_\_.py

```python
from python_tty.executor.executor import CommandExecutor
from python_tty.executor.models import Invocation, RunState, RunStatus

__all__ = [
    "CommandExecutor",
    "Invocation",
    "RunState",
    "RunStatus",
]
```

#### (M)execution.py
```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import COMMAND_REGISTRY
from python_tty.consoles.registry import REGISTRY
from python_tty.executor.models import Invocation


@dataclass
class ExecutionContext:
    source: str
    principal: Optional[str] = None
    console_name: Optional[str] = None
    command_name: Optional[str] = None
    command_id: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    raw_cmd: Optional[str] = None
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    timeout_ms: Optional[int] = None
    lock_key: str = "global"
    audit_policy: Optional[str] = None
    meta_revision: Optional[str] = None

    def to_invocation(self) -> Invocation:
        command_id = self.command_id
        if command_id is None and self.console_name and self.command_name:
            command_id = _build_command_id(self.console_name, self.command_name)
        return Invocation(
            run_id=self.run_id,
            source=self.source,
            principal=self.principal,
            console_id=self.console_name,
            command_id=command_id,
            command_name=self.command_name,
            argv=list(self.argv),
            kwargs=dict(self.kwargs),
            lock_key=self.lock_key,
            timeout_ms=self.timeout_ms,
            audit_policy=self.audit_policy,
            session_id=self.session_id,
            meta_revision=self.meta_revision,
            raw_cmd=self.raw_cmd,
        )


class ExecutionBinding:
    def __init__(self, service=None, manager=None, ctx: Optional[ExecutionContext] = None, console=None):
        self.service = service
        self.manager = manager
        self.ctx = ctx
        self._console = console
        self._commands = None

    def execute(self, invocation: Invocation):
        commands = self._get_commands(invocation)
        command_def = commands.get_command_def_by_id(invocation.command_id)
        if command_def is None and invocation.command_name is not None:
            command_def = commands.get_command_def(invocation.command_name)
        if command_def is None:
            raise ValueError(f"Command not found: {invocation.command_id}")
        if not invocation.argv:
            return command_def.func(commands)
        return command_def.func(commands, *invocation.argv)

    def _get_commands(self, invocation: Invocation):
        if self._commands is not None:
            return self._commands
        if self._console is not None and getattr(self._console, "commands", None) is not None:
            self._commands = self._console.commands
            return self._commands
        console_name = _resolve_console_name(self.ctx, invocation)
        console_cls = _resolve_console_cls(console_name)
        if console_cls is None:
            raise ValueError(f"Console not found: {console_name}")
        console_stub = console_cls.__new__(console_cls)
        console_stub.manager = self.manager
        console_stub.service = self.service
        console_stub.console_name = console_name
        commands_cls = COMMAND_REGISTRY.get_commands_cls(console_cls)
        if commands_cls is None:
            commands_cls = DefaultCommands
        self._commands = commands_cls(console_stub)
        return self._commands


def _resolve_console_name(ctx: Optional[ExecutionContext], invocation: Invocation) -> Optional[str]:
    if ctx is not None and ctx.console_name:
        return ctx.console_name
    return invocation.console_id


def _resolve_console_cls(console_name: Optional[str]):
    if console_name is None:
        return None
    for name, console_cls, _ in REGISTRY.iter_consoles():
        if name == console_name:
            return console_cls
    return None


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"
```

#### (M)executor.py

```python
import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from python_tty.config import ExecutorConfig
from python_tty.runtime.context import use_run_context
from python_tty.runtime.events import RuntimeEvent, RuntimeEventKind, UIEventLevel
from python_tty.runtime.jobs import JobStore
from python_tty.executor.models import Invocation, RunState, RunStatus
from python_tty.exceptions.console_exception import ConsoleExit, SubConsoleExit


@dataclass
class WorkItem:
    invocation: Invocation
    handler: Callable[[Invocation], object]


class CommandExecutor:
    def __init__(self, workers: int = 1, loop=None, config: ExecutorConfig = None):
        if config is None:
            config = ExecutorConfig(workers=workers)
        self._config = config
        self._worker_count = config.workers
        self._loop = loop
        self._queue = None
        self._workers = []
        self._locks: Dict[str, asyncio.Lock] = {}
        self._job_store = JobStore(
            retain_last_n=config.retain_last_n,
            ttl_seconds=config.ttl_seconds,
            event_history_max=config.event_history_max,
            event_history_ttl=config.event_history_ttl,
        )
        self._pop_on_wait = config.pop_on_wait
        self._emit_run_events = config.emit_run_events
        if config.exempt_exceptions is None:
            self._exempt_exceptions = (ConsoleExit, SubConsoleExit, asyncio.CancelledError)
        else:
            self._exempt_exceptions = tuple(config.exempt_exceptions)
        self._audit_sink = self._init_audit_sink(config)

    @property
    def runs(self):
        return self._job_store.runs

    @property
    def job_store(self):
        return self._job_store

    @property
    def audit_sink(self):
        return self._audit_sink

    def start(self, loop=None):
        if loop is not None:
            self._loop = loop
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError("Executor start requires a running event loop") from exc
        self._job_store.set_loop(self._loop)
        if self._queue is None:
            self._queue = asyncio.Queue()
        if self._workers:
            return
        for _ in range(self._worker_count):
            self._workers.append(self._loop.create_task(self._worker_loop()))

    def submit(self, invocation: Invocation, handler: Optional[Callable[[Invocation], object]] = None) -> str:
        if invocation.run_id is None:
            invocation.run_id = str(uuid.uuid4())
        if handler is None:
            handler = self._missing_handler
        run_id = invocation.run_id
        run_state = self._job_store.create_run(invocation)
        self._audit_invocation(invocation)
        self._audit_run_state(run_state)
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        if self._loop is None or not self._loop.is_running():
            self._run_inline(invocation, handler)
            return run_id
        self.start()
        self._job_store.set_future(run_id, self._loop.create_future())
        self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))
        return run_id

    async def wait_result(self, run_id: str):
        try:
            return await self._job_store.result(run_id)
        finally:
            if self._pop_on_wait:
                self.pop_run(run_id)

    def wait_result_sync(self, run_id: str, timeout: Optional[float] = None):
        try:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is not None and running_loop == self._loop:
                raise RuntimeError("wait_result_sync cannot be called from the executor loop thread")
            future = self._job_store.get_future(run_id)
            if future is not None and self._loop is not None and self._loop.is_running():
                result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
                return result_future.result(timeout)
            run_state = self._job_store.get_run_state(run_id)
            if run_state is None:
                return None
            if run_state.status in (RunStatus.PENDING, RunStatus.RUNNING):
                if self._loop is not None and self._loop.is_running():
                    result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
                    return result_future.result(timeout)
                raise RuntimeError("Run is still pending but executor loop is not running")
            if run_state.error is not None:
                raise run_state.error
            return run_state.result
        finally:
            if self._pop_on_wait:
                self.pop_run(run_id)

    def cancel(self, run_id: str) -> str:
        status = self._job_store.cancel(run_id)
        if status == "cancelled":
            invocation = self._job_store.get_invocation(run_id)
            source = getattr(invocation, "source", None)
            run_state = self._job_store.get_run_state(run_id)
            if run_state is not None:
                self._audit_run_state(run_state)
            self._emit_run_event(run_id, "cancelled", UIEventLevel.INFO, source=source, force=True)
        elif status == "requested":
            invocation = self._job_store.get_invocation(run_id)
            source = getattr(invocation, "source", None)
            self._emit_run_event(run_id, "cancel_requested", UIEventLevel.INFO, source=source, force=True)
        return status

    def stream_events(self, run_id: str, since_seq: int = 0):
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        return self._ensure_event_subscription(run_id, since_seq)

    def publish_event(self, run_id: str, event):
        if getattr(event, "run_id", None) is None:
            event.run_id = run_id
        if run_id is not None and getattr(event, "seq", None) is None:
            event.seq = self._job_store.next_event_seq(run_id)
        if self._loop is not None and self._loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop == self._loop:
                self._job_store.publish_event(run_id, event)
            else:
                self._loop.call_soon_threadsafe(self._job_store.publish_event, run_id, event)
        else:
            self._job_store.publish_event(run_id, event)
        if self._audit_sink is not None:
            self._audit_sink.record_event(event)

    async def shutdown(self, wait: bool = True):
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        if wait and workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._close_audit_sink()

    def shutdown_threadsafe(self, wait: bool = True, timeout: Optional[float] = None):
        loop = self._loop
        if loop is None or not loop.is_running():
            for task in list(self._workers):
                task.cancel()
            self._workers.clear()
            self._close_audit_sink()
            return None
        future = asyncio.run_coroutine_threadsafe(self.shutdown(wait=wait), loop)
        return future.result(timeout)

    def submit_threadsafe(self, invocation: Invocation,
                          handler: Optional[Callable[[Invocation], object]] = None) -> str:
        if invocation.run_id is None:
            invocation.run_id = str(uuid.uuid4())
        if handler is None:
            handler = self._missing_handler
        run_id = invocation.run_id
        if self._loop is None or not self._loop.is_running():
            return self.submit(invocation, handler=handler)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self.submit(invocation, handler=handler)
        run_state = self._job_store.create_run(invocation)
        self._audit_invocation(invocation)
        self._audit_run_state(run_state)

        async def _enqueue():
            self.start()
            self._job_store.set_future(run_id, self._loop.create_future())
            self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))

        asyncio.run_coroutine_threadsafe(_enqueue(), self._loop).result()
        return run_id

    async def _worker_loop(self):
        while True:
            work_item = await self._queue.get()
            run_state = self._job_store.get_run_state(work_item.invocation.run_id)
            lock = self._locks.setdefault(work_item.invocation.lock_key, asyncio.Lock())
            async with lock:
                await self._execute_work_item(work_item, run_state)
            self._queue.task_done()

    async def _execute_work_item(self, work_item: WorkItem, run_state: Optional[RunState]):
        if run_state is None:
            return
        if run_state.status == RunStatus.CANCELLED:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=work_item.invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            cancel_flag = self._job_store.get_cancel_flag(run_state.run_id)
            with use_run_context(run_id=run_state.run_id,
                                 source=work_item.invocation.source,
                                 emitter=emitter,
                                 cancel_flag=cancel_flag):
                timeout = self._timeout_seconds(work_item.invocation)
                result = await self._run_handler(work_item.invocation, work_item.handler, timeout)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=work_item.invocation.source)
            self._resolve_future(run_state, result=result)
        except asyncio.TimeoutError as exc:
            run_state.error = exc
            run_state.status = RunStatus.TIMEOUT
            self._emit_run_event(run_state.run_id, "timeout", UIEventLevel.WARNING,
                                 source=work_item.invocation.source, force=True)
            self._resolve_future(run_state, error=exc)
        except self._exempt_exceptions as exc:
            run_state.error = exc
            run_state.status = RunStatus.CANCELLED
            self._emit_run_event(run_state.run_id, "cancelled", UIEventLevel.INFO,
                                 source=work_item.invocation.source)
            self._resolve_future(run_state, error=exc)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self._emit_run_event(
                run_state.run_id,
                "failure",
                UIEventLevel.ERROR,
                payload={"error": str(exc)},
                source=work_item.invocation.source,
                force=True,
            )
            self._resolve_future(run_state, error=exc)
        finally:
            run_state.finished_at = time.time()
            self._audit_run_state(run_state)
            self._job_store.cleanup()

    def _resolve_future(self, run_state: RunState, result=None, error: Optional[BaseException] = None):
        self._job_store.resolve_future(run_state.run_id, result=result, error=error)

    def _run_inline(self, invocation: Invocation, handler):
        run_state = self._job_store.get_run_state(invocation.run_id)
        if run_state is None:
            return
        if run_state.status == RunStatus.CANCELLED:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self._audit_run_state(run_state)
        self._emit_run_event(run_state.run_id, "start", UIEventLevel.INFO, source=invocation.source)
        try:
            emitter = lambda event: self.publish_event(run_state.run_id, event)
            cancel_flag = self._job_store.get_cancel_flag(run_state.run_id)
            with use_run_context(run_id=run_state.run_id,
                                 source=invocation.source,
                                 emitter=emitter,
                                 cancel_flag=cancel_flag):
                timeout = self._timeout_seconds(invocation)
                result = self._run_handler_inline(invocation, handler, timeout)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self._emit_run_event(run_state.run_id, "success", UIEventLevel.SUCCESS,
                                 source=invocation.source)
        except asyncio.TimeoutError as exc:
            run_state.error = exc
            run_state.status = RunStatus.TIMEOUT
            self._emit_run_event(run_state.run_id, "timeout", UIEventLevel.WARNING,
                                 source=invocation.source, force=True)
        except self._exempt_exceptions as exc:
            run_state.error = exc
            run_state.status = RunStatus.CANCELLED
            self._emit_run_event(run_state.run_id, "cancelled", UIEventLevel.INFO,
                                 source=invocation.source)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self._emit_run_event(
                run_state.run_id,
                "failure",
                UIEventLevel.ERROR,
                payload={"error": str(exc)},
                source=invocation.source,
                force=True,
            )
        finally:
            run_state.finished_at = time.time()
            self._audit_run_state(run_state)
            self._job_store.cleanup()

    @staticmethod
    def _build_run_event(event_type: str, level: UIEventLevel, payload=None, source=None):
        return RuntimeEvent(
            kind=RuntimeEventKind.STATE,
            msg=event_type,
            level=level,
            event_type=event_type,
            payload=payload,
            source=source,
        )

    def _emit_run_event(self, run_id: str, event_type: str, level: UIEventLevel,
                        payload=None, source=None, force: bool = False):
        if force or self._emit_run_events:
            self.publish_event(run_id, self._build_run_event(event_type, level, payload=payload, source=source))

    @staticmethod
    def _missing_handler(invocation: Invocation):
        raise RuntimeError("No handler provided for invocation execution")

    @staticmethod
    def _timeout_seconds(invocation: Invocation) -> Optional[float]:
        timeout_ms = getattr(invocation, "timeout_ms", None)
        if timeout_ms is None:
            return None
        return max(0.0, timeout_ms / 1000.0)

    async def _run_handler(self, invocation: Invocation, handler, timeout: Optional[float]):
        start = time.monotonic()
        result = handler(invocation)
        if inspect.isawaitable(result):
            if timeout is None:
                return await result
            return await asyncio.wait_for(result, timeout)
        if timeout is not None:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError()
        return result

    def _run_handler_inline(self, invocation: Invocation, handler, timeout: Optional[float]):
        start = time.monotonic()
        result = handler(invocation)
        if inspect.isawaitable(result):
            if timeout is None:
                return self._run_awaitable_inline(result)
            return self._run_awaitable_inline(self._awaitable_with_timeout(result, timeout))
        if timeout is not None:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError()
        return result

    @staticmethod
    async def _awaitable_with_timeout(awaitable, timeout: float):
        return await asyncio.wait_for(awaitable, timeout)

    def _ensure_event_subscription(self, run_id: str, since_seq: int = 0):
        if self._loop is None or not self._loop.is_running():
            return self._job_store.events(run_id, since_seq)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self._job_store.events(run_id, since_seq)
        future = asyncio.run_coroutine_threadsafe(
            self._create_event_subscription(run_id, since_seq),
            self._loop,
        )
        return future.result()

    async def _create_event_subscription(self, run_id: str, since_seq: int = 0):
        return self._job_store.events(run_id, since_seq)

    def _init_audit_sink(self, config: ExecutorConfig):
        audit_config = getattr(config, "audit", None)
        if audit_config is None or not audit_config.enabled:
            return None
        if audit_config.sink is not None:
            return audit_config.sink
        from python_tty.audit import AuditSink
        return AuditSink(
            file_path=audit_config.file_path,
            stream=audit_config.stream,
            keep_in_memory=audit_config.keep_in_memory,
            async_mode=audit_config.async_mode,
            flush_interval=audit_config.flush_interval,
        )

    def _audit_invocation(self, invocation: Invocation):
        if self._audit_sink is None:
            return
        self._audit_sink.record_invocation(invocation)

    def _audit_run_state(self, run_state: RunState):
        if self._audit_sink is None:
            return
        self._audit_sink.record_run_state(run_state)

    def _close_audit_sink(self):
        if self._audit_sink is None:
            return
        self._audit_sink.close()

    def _run_awaitable_inline(self, awaitable):
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if asyncio.isfuture(awaitable):
            raise RuntimeError("Inline awaitable must be a coroutine, not a Future/Task")
        if running_loop is None:
            return asyncio.run(self._awaitable_to_coroutine(awaitable))
        if self._loop is not None and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._awaitable_to_coroutine(awaitable),
                self._loop,
            )
            return future.result()
        raise RuntimeError("Cannot run awaitable inline while an event loop is running")

    @staticmethod
    def _awaitable_to_coroutine(awaitable):
        if asyncio.iscoroutine(awaitable):
            return awaitable

        async def _await_obj():
            return await awaitable

        return _await_obj()

    def pop_run(self, run_id: str):
        return self._job_store.pop_run(run_id)
```

#### (M)model.py

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class Invocation:
    run_id: Optional[str] = None
    source: str = "tty"
    principal: Optional[str] = None
    console_id: Optional[str] = None
    command_id: Optional[str] = None
    command_name: Optional[str] = None
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    lock_key: str = "global"
    timeout_ms: Optional[int] = None
    audit_policy: Optional[str] = None
    session_id: Optional[str] = None
    meta_revision: Optional[str] = None
    raw_cmd: Optional[str] = None


@dataclass
class RunState:
    run_id: str
    status: RunStatus = RunStatus.PENDING
    result: Any = None
    error: Optional[BaseException] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
```

### frontends

#### (M)__init\_\_.py

```python
```

#### rpc

##### (M)__init\_\_.py

```python
```

#### web

##### (M)__init\_\_.py

```python
```

### meta

#### (M)__init\_\_.py

```python
import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

from python_tty.commands.mixins import DefaultCommands
from python_tty.commands.registry import ArgSpec, COMMAND_REGISTRY
from python_tty.consoles.registry import REGISTRY


@dataclass
class _ConsoleEntry:
    name: str
    console_cls: type
    parent: Optional[str]


def export_meta(console_registry=REGISTRY, command_registry=COMMAND_REGISTRY,
                include_default_commands: bool = True):
    """Export console/command metadata as a dict with a revision hash."""
    consoles = []
    entries = _collect_console_entries(console_registry)
    for entry in entries:
        command_defs = command_registry.get_command_defs_for_console(entry.console_cls)
        if not command_defs and include_default_commands:
            command_defs = command_registry.collect_from_commands_cls(DefaultCommands)
        commands = _export_commands(entry.name, command_defs)
        consoles.append({
            "name": entry.name,
            "parent": entry.parent,
            "type": entry.console_cls.__name__,
            "module": entry.console_cls.__module__,
            "commands": commands,
        })
    consoles.sort(key=lambda item: item["name"])
    meta = {
        "version": 1,
        "consoles": consoles,
    }
    tree = None
    if hasattr(console_registry, "get_console_tree"):
        tree = console_registry.get_console_tree()
    if tree is not None:
        meta["tree"] = tree
    console_map = None
    if hasattr(console_registry, "get_console_map"):
        console_map = console_registry.get_console_map()
    if console_map is not None:
        meta["console_map"] = console_map
    meta["revision"] = _compute_revision(meta)
    return meta


def _collect_console_entries(console_registry):
    entries: List[_ConsoleEntry] = []
    iter_consoles = getattr(console_registry, "iter_consoles", None)
    if not callable(iter_consoles):
        raise RuntimeError("Console registry must implement iter_consoles()")
    for name, console_cls, parent in iter_consoles():
        entries.append(_ConsoleEntry(name=name, console_cls=console_cls, parent=parent))
    return entries


def _export_commands(console_name: str, command_defs):
    commands = []
    for command_def in command_defs or []:
        arg_spec = command_def.arg_spec or ArgSpec.from_signature(command_def.func)
        commands.append({
            "id": _build_command_id(console_name, command_def.func_name),
            "name": command_def.func_name,
            "aliases": list(command_def.alias or []),
            "description": command_def.func_description,
            "argspec": {
                "min": arg_spec.min_args,
                "max": arg_spec.max_args,
                "variadic": arg_spec.variadic,
            },
        })
    commands.sort(key=lambda item: item["id"])
    return commands


def _build_command_id(console_name: str, command_name: str):
    return f"cmd:{console_name}:{command_name}"


def _compute_revision(meta):
    payload = dict(meta)
    payload.pop("revision", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "export_meta",
]
```



### runtime

#### (M)\_\_init\_\_.py

```python
from python_tty.runtime.events import (
    EventBase,
    RuntimeEvent,
    RuntimeEventKind,
    UIEvent,
    UIEventLevel,
    UIEventListener,
    UIEventSpeaker,
)
from python_tty.runtime.context import (
    get_current_emitter,
    get_current_run_id,
    get_current_source,
    get_current_cancel_flag,
    is_cancelled,
    use_run_context,
)
from python_tty.runtime.event_bus import RunEventBus
from python_tty.runtime.jobs import JobStore
from python_tty.runtime.provider import get_default_router, get_router, set_default_router, use_router
from python_tty.runtime.router import BaseRouter, OutputRouter, get_output_router, proxy_print
from python_tty.runtime.sinks import TTYEventSink

__all__ = [
    "UIEvent",
    "UIEventLevel",
    "EventBase",
    "RuntimeEvent",
    "RuntimeEventKind",
    "UIEventListener",
    "UIEventSpeaker",
    "RunEventBus",
    "JobStore",
    "TTYEventSink",
    "get_current_run_id",
    "get_current_source",
    "get_current_emitter",
    "get_current_cancel_flag",
    "is_cancelled",
    "use_run_context",
    "BaseRouter",
    "OutputRouter",
    "get_default_router",
    "get_router",
    "get_output_router",
    "set_default_router",
    "proxy_print",
    "use_router",
]
```

#### (M)context.py

```python
import contextvars
from contextlib import contextmanager
from typing import Callable, Optional


_CURRENT_RUN_ID = contextvars.ContextVar("python_tty_current_run_id", default=None)
_CURRENT_SOURCE = contextvars.ContextVar("python_tty_current_source", default=None)
_CURRENT_EMITTER = contextvars.ContextVar("python_tty_current_emitter", default=None)
_CURRENT_CANCEL_FLAG = contextvars.ContextVar("python_tty_current_cancel_flag", default=None)


def get_current_run_id() -> Optional[str]:
    return _CURRENT_RUN_ID.get()


def get_current_source() -> Optional[str]:
    return _CURRENT_SOURCE.get()


def get_current_emitter() -> Optional[Callable[[object], None]]:
    return _CURRENT_EMITTER.get()


def get_current_cancel_flag():
    return _CURRENT_CANCEL_FLAG.get()


def is_cancelled() -> bool:
    flag = get_current_cancel_flag()
    return bool(flag.is_set()) if flag is not None else False


@contextmanager
def use_run_context(run_id: Optional[str] = None,
                    source: Optional[str] = None,
                    emitter: Optional[Callable[[object], None]] = None,
                    cancel_flag=None):
    run_token = _CURRENT_RUN_ID.set(run_id)
    source_token = _CURRENT_SOURCE.set(source)
    emitter_token = _CURRENT_EMITTER.set(emitter)
    cancel_token = _CURRENT_CANCEL_FLAG.set(cancel_flag)
    try:
        yield
    finally:
        _CURRENT_RUN_ID.reset(run_token)
        _CURRENT_SOURCE.reset(source_token)
        _CURRENT_EMITTER.reset(emitter_token)
        _CURRENT_CANCEL_FLAG.reset(cancel_token)
```

#### (M)event\_bus.py

```python
import asyncio
import time
from typing import Dict, List, Optional


class RunEventBus:
    def __init__(self, max_events: Optional[int] = None, ttl_seconds: Optional[float] = None):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[object]] = {}
        self._max_events = max_events
        self._ttl_seconds = ttl_seconds

    def publish(self, run_id: Optional[str], event: object):
        if run_id is None:
            return
        self._history.setdefault(run_id, []).append(event)
        self._prune_history(run_id)
        for queue in list(self._subscribers.get(run_id, [])):
            queue.put_nowait(event)

    def subscribe(self, run_id: str, since_seq: int = 0) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        if since_seq is not None and since_seq >= 0:
            for event in self._history.get(run_id, []):
                seq = getattr(event, "seq", 0) or 0
                if seq > since_seq:
                    queue.put_nowait(event)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        try:
            subscribers.remove(queue)
        except ValueError:
            return
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def drop(self, run_id: str):
        self._subscribers.pop(run_id, None)
        self._history.pop(run_id, None)

    def _prune_history(self, run_id: str):
        history = self._history.get(run_id)
        if not history:
            return
        if self._ttl_seconds is not None:
            cutoff = time.time() - self._ttl_seconds
            while history:
                ts = getattr(history[0], "ts", None)
                if ts is None or ts >= cutoff:
                    break
                history.pop(0)
        if self._max_events is not None and self._max_events >= 0:
            if len(history) > self._max_events:
                del history[:-self._max_events]
```

#### (M)events.py

```python
import enum
import time


class UIEventLevel(enum.Enum):
    TEXT = -1
    INFO = 0
    WARNING = 1
    ERROR = 2
    SUCCESS = 3
    FAILURE = 4
    DEBUG = 5

    @staticmethod
    def map_level(code):
        if code == 0:
            return UIEventLevel.INFO
        elif code == 1:
            return UIEventLevel.WARNING
        elif code == 2:
            return UIEventLevel.ERROR
        elif code == 3:
            return UIEventLevel.SUCCESS
        elif code == 4:
            return UIEventLevel.FAILURE
        elif code == 5:
            return UIEventLevel.DEBUG


class RuntimeEventKind(enum.Enum):
    STATE = "state"
    STDOUT = "stdout"
    LOG = "log"


def _normalize_runtime_kind(kind):
    if isinstance(kind, RuntimeEventKind):
        return kind
    if kind is None:
        return None
    try:
        return RuntimeEventKind(kind)
    except ValueError:
        return None


class EventBase:
    """Common event fields shared by RuntimeEvent and UIEvent."""
    def __init__(self, msg, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        self.msg = msg
        self.level = level
        self.run_id = run_id
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.ts = time.time() if ts is None else ts
        self.seq = seq


class UIEvent(EventBase):
    """UI event payload for rendering.

    Fields:
        msg: Display text or structured data for the event.
        level: UIEventLevel (or int) that drives rendering style.
        run_id: Run identifier when the event is tied to a command invocation.
        event_type: A short event type label (e.g., "start", "success").
        payload: Structured payload for downstream consumers.
        source: Event origin (framework should pass "tty"/"rpc" explicitly;
            external callers via proxy_print default to "custom").
        ts: Unix timestamp (seconds) when the event was created.
        seq: Per-run sequence number when emitted by the executor.
    """
    def __init__(self, msg, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        super().__init__(
            msg=msg,
            level=level,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            source=source,
            ts=ts,
            seq=seq,
        )


class RuntimeEvent(EventBase):
    """Runtime event payload for executor/audit pipelines.

    Fields:
        kind: RuntimeEventKind (state/stdout/log).
        msg: Text or payload for stdout/log events.
        level: UIEventLevel or int for log/stdout severity.
        run_id: Run identifier for correlation.
        event_type: State label for state events (e.g., "start", "success").
        payload: Structured payload for downstream consumers.
        source: Event origin (framework should pass "tty"/"rpc").
        ts: Unix timestamp (seconds) when the event was created.
        seq: Per-run sequence number assigned by the executor.
    """
    def __init__(self, kind, msg=None, level=UIEventLevel.TEXT, run_id=None, event_type=None,
                 payload=None, source=None, ts=None, seq=None):
        self.kind = _normalize_runtime_kind(kind)
        super().__init__(
            msg=msg,
            level=level,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            source=source,
            ts=ts,
            seq=seq,
        )

    def to_ui_event(self):
        return UIEvent(
            msg=self.msg,
            level=self.level,
            run_id=self.run_id,
            event_type=self.event_type,
            payload=self.payload,
            source=self.source,
            ts=self.ts,
            seq=self.seq,
        )


class UIEventListener:
    def handler_event(self, event: UIEvent):
        pass


class UIEventSpeaker:
    def __init__(self):
        self._event_listener = []

    def add_event_listener(self, listener: UIEventListener):
        self._event_listener.append(listener)

    def remove_event_listener(self, listener: UIEventListener):
        self._event_listener.remove(listener)

    def notify_event_listeners(self, event: UIEvent):
        for listener in self._event_listener:
            listener.handler_event(event)
```

#### (M)jobs.py
```python
import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from python_tty.executor.models import Invocation, RunState, RunStatus
from python_tty.runtime.event_bus import RunEventBus


class JobStore:
    def __init__(self,
                 retain_last_n: Optional[int] = None,
                 ttl_seconds: Optional[float] = None,
                 event_history_max: Optional[int] = None,
                 event_history_ttl: Optional[float] = None):
        self._runs: Dict[str, RunState] = {}
        self._invocations: Dict[str, Invocation] = {}
        self._run_futures: Dict[str, asyncio.Future] = {}
        self._event_seq: Dict[str, int] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._event_bus = RunEventBus(
            max_events=event_history_max,
            ttl_seconds=event_history_ttl,
        )
        self._retain_last_n = retain_last_n
        self._ttl_seconds = ttl_seconds
        self._loop = None
        self._global_subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()

    @property
    def runs(self):
        return self._runs

    def set_loop(self, loop):
        self._loop = loop

    def create_run(self, invocation: Invocation) -> RunState:
        run_id = invocation.run_id
        if run_id is None:
            raise ValueError("Invocation run_id is required for JobStore")
        run_state = RunState(run_id=run_id)
        with self._lock:
            self._runs[run_id] = run_state
            self._invocations[run_id] = invocation
            self._cancel_flags[run_id] = threading.Event()
        return run_state

    def set_future(self, run_id: str, future: asyncio.Future):
        with self._lock:
            self._run_futures[run_id] = future

    def get_future(self, run_id: str):
        with self._lock:
            return self._run_futures.get(run_id)

    def get_run_state(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            return self._runs.get(run_id)

    def get_invocation(self, run_id: str) -> Optional[Invocation]:
        with self._lock:
            return self._invocations.get(run_id)

    def get(self, run_id: str):
        with self._lock:
            return {
                "run_state": self._runs.get(run_id),
                "invocation": self._invocations.get(run_id),
            }

    def list(self, filters: Optional[Dict[str, Any]] = None):
        filters = filters or {}
        status_filter = _normalize_filter(filters.get("status"))
        source_filter = _normalize_filter(filters.get("source"))
        principal_filter = _normalize_filter(filters.get("principal"))
        command_filter = _normalize_filter(filters.get("command_id"))
        results = []
        with self._lock:
            runs = list(self._runs.items())
            invocations = dict(self._invocations)
        for run_id, run_state in runs:
            invocation = invocations.get(run_id)
            if status_filter and run_state.status not in status_filter:
                continue
            if source_filter and invocation is not None and invocation.source not in source_filter:
                continue
            if principal_filter and invocation is not None and invocation.principal not in principal_filter:
                continue
            if command_filter and invocation is not None and invocation.command_id not in command_filter:
                continue
            results.append({
                "run_id": run_id,
                "status": run_state.status,
                "source": getattr(invocation, "source", None),
                "principal": getattr(invocation, "principal", None),
                "command_id": getattr(invocation, "command_id", None),
                "started_at": run_state.started_at,
                "finished_at": run_state.finished_at,
            })
        return results

    async def result(self, run_id: str):
        future = self.get_future(run_id)
        if future is None:
            run_state = self.get_run_state(run_id)
            if run_state is None:
                return None
            if run_state.error is not None:
                raise run_state.error
            return run_state.result
        return await future

    def resolve_future(self, run_id: str, result=None, error: Optional[BaseException] = None):
        future = self.get_future(run_id)
        if future is None or future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def next_event_seq(self, run_id: str) -> int:
        with self._lock:
            next_seq = self._event_seq.get(run_id, 0) + 1
            self._event_seq[run_id] = next_seq
        return next_seq

    def publish_event(self, run_id: str, event: object):
        self._event_bus.publish(run_id, event)
        with self._lock:
            subscribers = list(self._global_subscribers)
        for queue in subscribers:
            queue.put_nowait(event)

    def events(self, run_id: str, since_seq: int = 0) -> asyncio.Queue:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and (self._loop is None or running_loop == self._loop):
            return self._event_bus.subscribe(run_id, since_seq)
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("events requires a running event loop")
        future = asyncio.run_coroutine_threadsafe(
            self._create_event_subscription(run_id, since_seq),
            self._loop,
        )
        return future.result()

    def subscribe_all(self) -> asyncio.Queue:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and (self._loop is None or running_loop == self._loop):
            queue: asyncio.Queue = asyncio.Queue()
            with self._lock:
                self._global_subscribers.append(queue)
            return queue
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("subscribe_all requires a running event loop")
        future = asyncio.run_coroutine_threadsafe(self._create_global_subscription(), self._loop)
        return future.result()

    async def _create_global_subscription(self):
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._global_subscribers.append(queue)
        return queue

    async def _create_event_subscription(self, run_id: str, since_seq: int = 0):
        return self._event_bus.subscribe(run_id, since_seq)

    def unsubscribe_all(self, queue: asyncio.Queue):
        with self._lock:
            try:
                self._global_subscribers.remove(queue)
            except ValueError:
                return

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            flag = self._cancel_flags.get(run_id)
            if flag is None:
                return False
            return flag.is_set()

    def get_cancel_flag(self, run_id: str):
        with self._lock:
            return self._cancel_flags.get(run_id)

    def cancel(self, run_id: str) -> str:
        with self._lock:
            run_state = self._runs.get(run_id)
            if run_state is None:
                return "missing"
            flag = self._cancel_flags.get(run_id)
            if flag is not None:
                flag.set()
            if run_state.status == RunStatus.PENDING:
                run_state.status = RunStatus.CANCELLED
                run_state.finished_at = time.time()
                run_state.error = asyncio.CancelledError()
                future = self._run_futures.get(run_id)
                if future is not None and not future.done():
                    future.set_exception(run_state.error)
                return "cancelled"
            if run_state.status == RunStatus.RUNNING:
                return "requested"
            return "noop"

    def pop_run(self, run_id: str):
        with self._lock:
            run_state = self._runs.pop(run_id, None)
            future = self._run_futures.pop(run_id, None)
            self._event_seq.pop(run_id, None)
            self._invocations.pop(run_id, None)
            self._cancel_flags.pop(run_id, None)
        if future is not None and not future.done():
            future.cancel()
        self._event_bus.drop(run_id)
        return run_state

    def cleanup(self):
        if self._retain_last_n is None and self._ttl_seconds is None:
            return
        now = time.time()
        completed = []
        with self._lock:
            runs = list(self._runs.items())
        for run_id, run_state in runs:
            if run_state.status in (RunStatus.PENDING, RunStatus.RUNNING):
                continue
            completed.append((run_state.finished_at, run_id))
        remove_ids = set()
        if self._ttl_seconds is not None:
            for finished_at, run_id in completed:
                if finished_at is None:
                    continue
                if now - finished_at >= self._ttl_seconds:
                    remove_ids.add(run_id)
        if self._retain_last_n is not None and self._retain_last_n >= 0:
            completed.sort(reverse=True)
            for _, run_id in completed[self._retain_last_n:]:
                remove_ids.add(run_id)
        for run_id in remove_ids:
            self.pop_run(run_id)


def _normalize_filter(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value}
```

#### (M)router.py

```python
import threading
from abc import ABC, abstractmethod
from typing import Optional

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style

from python_tty.runtime.context import get_current_emitter, get_current_run_id, get_current_source
from python_tty.runtime.events import RuntimeEvent, RuntimeEventKind, UIEvent, UIEventLevel
from python_tty.runtime.provider import get_router


MSG_LEVEL_SYMBOL = {
    0: "[*] ",
    1: "[!] ",
    2: "[x] ",
    3: "[+] ",
    4: "[-] ",
    5: "[@] "
}

MSG_LEVEL_SYMBOL_STYLE = {
    0: "fg:green",
    1: "fg:yellow",
    2: "fg:red",
    3: "fg:blue",
    4: "fg:white",
    5: "fg:pink"
}


class BaseRouter(ABC):
    @abstractmethod
    def emit(self, event):
        raise NotImplementedError


class OutputRouter(BaseRouter):
    def __init__(self):
        self._lock = threading.Lock()
        self._app = None
        self._output = None

    def bind_session(self, session):
        if session is None:
            return
        with self._lock:
            self._app = getattr(session, "app", None)
            self._output = getattr(session, "output", None)

    def clear_session(self, session=None):
        with self._lock:
            if session is None or getattr(session, "app", None) == self._app:
                self._app = None
                self._output = None

    def emit(self, event):
        audit_event = event
        if isinstance(event, RuntimeEvent):
            if event.kind in (RuntimeEventKind.STDOUT, RuntimeEventKind.STATE, RuntimeEventKind.LOG):
                event = event.to_ui_event()
            else:
                return
        with self._lock:
            app = self._app
            output = self._output

        def _render():
            text, style = _format_event(event)
            if output is not None:
                print_formatted_text(text, style=style, output=output)
            else:
                print_formatted_text(text, style=style)

        if app is not None and getattr(app, "is_running", False):
            if hasattr(app, "call_from_executor") and hasattr(app, "run_in_terminal"):
                app.call_from_executor(lambda: app.run_in_terminal(_render))
                return
        _render()


def _normalize_level(level):
    if isinstance(level, UIEventLevel):
        return level
    if level is None:
        return UIEventLevel.TEXT
    if level == UIEventLevel.TEXT.value:
        return UIEventLevel.TEXT
    mapped = UIEventLevel.map_level(level)
    return UIEventLevel.TEXT if mapped is None else mapped


def _format_event(event: UIEvent):
    level = _normalize_level(event.level)
    if level == UIEventLevel.TEXT:
        return event.msg, None
    formatted_text = FormattedText([
        ("class:level", MSG_LEVEL_SYMBOL[level.value]),
        ("class:text", str(event.msg)),
    ])
    style = Style.from_dict({
        "level": MSG_LEVEL_SYMBOL_STYLE[level.value]
    })
    return formatted_text, style


def get_output_router() -> Optional[BaseRouter]:
    return get_router()


def proxy_print(text="", text_type=UIEventLevel.TEXT, source="custom", run_id=None):
    """Emit a UIEvent for display.

    Args:
        text: Display text or object to render.
        text_type: UIEventLevel or int.
        source: Event source. Use "tty"/"rpc" for framework events.
            External callers can rely on the default "custom".
        run_id: Optional run identifier to correlate output with an invocation.
    """
    level = _normalize_level(text_type)
    context_run_id = get_current_run_id()
    emitter = get_current_emitter()
    if context_run_id is not None and emitter is not None:
        kind = RuntimeEventKind.STDOUT if level == UIEventLevel.TEXT else RuntimeEventKind.LOG
        event = RuntimeEvent(
            kind=kind,
            msg=text,
            level=level,
            run_id=context_run_id,
            source=get_current_source() or source,
        )
        emitter(event)
        return
    event = UIEvent(msg=text, level=level, source=source, run_id=run_id)
    router = get_router()
    if router is None:
        return
    router.emit(event)
```

#### (M)provider.py

```python
import contextvars
import threading
from contextlib import contextmanager
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from python_tty.runtime.router import BaseRouter


class RouterProvider:
    def __init__(self):
        self._default_router: Optional["BaseRouter"] = None
        self._lock = threading.Lock()
        self._current_router = contextvars.ContextVar("python_tty_current_router", default=None)

    def set_default_router(self, router: Optional["BaseRouter"]):
        with self._lock:
            self._default_router = router
        return router

    def get_default_router(self) -> Optional["BaseRouter"]:
        with self._lock:
            return self._default_router

    def get_router(self) -> Optional["BaseRouter"]:
        current = self._current_router.get()
        if current is not None:
            return current
        return self.get_default_router()

    def set_current_router(self, router: Optional["BaseRouter"]):
        return self._current_router.set(router)

    def reset_current_router(self, token):
        self._current_router.reset(token)

    @contextmanager
    def use_router(self, router: Optional["BaseRouter"]):
        token = self._current_router.set(router)
        try:
            yield router
        finally:
            self._current_router.reset(token)


_PROVIDER = RouterProvider()


def set_default_router(router):
    return _PROVIDER.set_default_router(router)


def get_default_router():
    return _PROVIDER.get_default_router()


def get_router():
    return _PROVIDER.get_router()


def use_router(router):
    return _PROVIDER.use_router(router)
```

#### (M)sinks.py

```python
import asyncio

class TTYEventSink:
    def __init__(self, job_store, router):
        self._job_store = job_store
        self._router = router
        self._task: asyncio.Task | None = None

    async def _run(self):
        queue = self._job_store.subscribe_all()
        try:
            while True:
                event = await queue.get()
                if self._router is None:
                    continue
                self._router.emit(event)
        except asyncio.CancelledError:
            raise
        finally:
            self._job_store.unsubscribe_all(queue)

    def start(self, loop):
        if self._task is not None:
            return
        self._task = loop.create_task(self._run())

    def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
```

### utils

#### (M)__init\_\_.py

```python
from python_tty.utils.table import Table
from python_tty.utils.tokenize import get_command_token, get_func_param_strs, split_cmd, tokenize_cmd

__all__ = [
    "Table",
    "get_command_token",
    "get_func_param_strs",
    "split_cmd",
    "tokenize_cmd",
]
```

#### (M)table.py

```python
import copy


class Cell:
    def __init__(self, data):
        self.data = data
        self.data_str = str(self.data)
        self.data_width = len(self.data_str)
        self.padding = ""

    def update_max_width(self, padding_len: int):
        if padding_len > 0:
            self.padding = " " * padding_len

    def __str__(self):
        return "".join([self.data_str, self.padding])


class HeaderCell(Cell):
    def __init__(self, data, seq="-"):
        super().__init__(data)
        self.seq_str = self.data_width * seq
        self.data_str = str(self.data)

    def get_seq_str(self):
        return "".join([self.seq_str, self.padding])


class Table:
    def __init__(self, header: [], data: [[]], title="",
                 title_indent=0, data_indent=4, data_seq_len=4,
                 title_seq="=", header_seq="-", header_footer=True):
        self.title = title
        self.title_indent = title_indent
        self.data_indent = data_indent
        self.data_seq_len = data_seq_len
        self.title_seq = title_seq
        self.header_seq = header_seq
        self.header_footer = header_footer
        self.header = copy.deepcopy(header)
        self.data = copy.deepcopy(data)
        self._padding_data()
        self._format_header()
        self._merge_data()
        self._padding_max_width()

    def _padding_data(self):
        table_header_item_num = len(self.header)
        for i in range(len(self.data)):
            row = self.data[i]
            if len(row) < table_header_item_num:
                self.data[i].append("")
            elif len(row) > table_header_item_num:
                self.data[i] = row[:table_header_item_num]

    def _format_header(self):
        for i in range(len(self.header)):
            cell = self.header[i]
            self.header[i] = str(cell)[0:1].upper() + str(cell)[1:]

    def _merge_data(self):
        data = []
        header = []
        for cell in self.header:
            header.append(HeaderCell(cell, self.header_seq))
        data.append(header)
        for row in self.data:
            line = []
            for cell in row:
                line.append(Cell(cell))
            data.append(line)
        self.data = data

    def _padding_max_width(self):
        max_widths = [len(cell) for cell in self.header]
        for i in range(len(self.data)):
            for j in range(len(self.data[i])):
                max_width = max_widths[j]
                cell = self.data[i][j]
                if cell.data_width > max_width:
                    max_widths[j] = cell.data_width
        for i in range(len(self.data)):
            for j in range(len(self.data[i])):
                max_width = max_widths[j]
                cell = self.data[i][j]
                if cell.data_width < max_width:
                    cell.update_max_width(max_width - cell.data_width)

    def print_row(self, row: []):
        cells = []
        seqs = []
        for cell in row:
            if isinstance(cell, HeaderCell):
                seqs.append(cell.get_seq_str())
            cells.append(str(cell))
        if len(seqs) > 0:
            return " "*self.data_indent + (" " * self.data_seq_len).join(cells),\
                " "*self.data_indent + (" " * self.data_seq_len).join(seqs)
        else:
            return " "*self.data_indent + (" " * self.data_seq_len).join(cells), None

    def print_data(self):
        lines = []
        for row in self.data:
            line, seq = self.print_row(row)
            lines.append(line)
            if seq is not None:
                lines.append(seq)
        return "\n".join(lines)

    def print_title(self):
        title_str = str(self.title)
        if title_str != "":
            if not title_str[0:1].isupper():
                title_str = title_str[0:1].upper() + title_str[1:].lower()
            title_line = " "*self.title_indent + title_str
            seq_line = " "*self.title_indent + self.title_seq*len(self.title)
            return "\n".join([title_line, seq_line])

    def __str__(self):
        if str(self.title) != "":
            title = self.print_title() + "\n\n"
            table_str = title + self.print_data()
        else:
            table_str = self.print_data()
        return "\n" + table_str + "\n" if self.header_footer else table_str
```

#### (M)tokenize.py

```python
import shlex


def tokenize_cmd(cmd: str):
    cmd = cmd.strip()
    if cmd == "":
        return []
    try:
        return shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise ValueError("Invalid command arguments") from exc


def get_command_token(cmd: str):
    tokens = tokenize_cmd(cmd)
    return tokens[0] if tokens else ""


def get_func_param_strs(cmd: str, param_count: int):
    if param_count <= 0:
        return None
    cmd = cmd.strip()
    if cmd == "":
        return []
    if param_count == 1:
        tokens = tokenize_cmd(cmd)
        if len(tokens) == 1:
            return tokens
        return [cmd]
    return tokenize_cmd(cmd)


def split_cmd(cmd: str):
    stripped = cmd.lstrip()
    if stripped == "":
        return "", "", []
    tokens = tokenize_cmd(stripped)
    if not tokens:
        return "", "", []
    token = tokens[0]
    if stripped.startswith(token):
        remainder = stripped[len(token):].lstrip()
    else:
        remainder = " ".join(tokens[1:])
    return token, remainder, tokens
```

