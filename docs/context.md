# src

### (M)__init.py\_\_

```python
from src.console_factory import ConsoleFactory
from src.core.events import UIEvent, UIEventLevel, UIEventListener, UIEventSpeaker
from src.ui.output import proxy_print

__all__ = [
    "UIEvent",
    "UIEventLevel",
    "UIEventListener",
    "UIEventSpeaker",
    "ConsoleFactory",
    "proxy_print",
]
```

### (M)console_factory.py

```python
from src.consoles.loader import load_consoles
from src.consoles.manager import ConsoleManager
from src.consoles.registry import REGISTRY
from src.executor import CommandExecutor


class ConsoleFactory:
    """Bootstrap console system by loading modules and registering consoles.

    Example:
        # Pass your business core instance here to make it available
        # to all console/commands classes via the manager service.
        factory = ConsoleFactory(object())
        factory.start()

    Notes:
        - To auto-load consoles, update DEFAULT_CONSOLE_MODULES in
          src.consoles.loader with the modules that define your console classes.
        - Or call load_consoles(...) yourself before starting to register
          consoles via their decorators.
    """
    def __init__(self, service=None, executor=None):
        if executor is None:
            executor = CommandExecutor()
        self.executor = executor
        self.manager = ConsoleManager(service=service, executor=executor, on_shutdown=self.shutdown)
        load_consoles()
        REGISTRY.register_all(self.manager)

    def start(self):
        """Start the console loop with the registered root console."""
        self.manager.run()

    def start_executor(self, loop=None):
        """Start executor workers on the provided asyncio loop."""
        self.executor.start(loop=loop)

    def shutdown_executor(self, wait=True, timeout=None):
        """Shutdown executor workers after RPC/TTY stop."""
        return self.executor.shutdown_threadsafe(wait=wait, timeout=timeout)

    def shutdown(self):
        """Shutdown all resources owned by the factory."""
        self.shutdown_executor()
```

## commands

### (M)__init.py\_\_

```python
from src.commands.core import BaseCommands, CommandValidator
from src.commands.registry import (
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

### core.py

```python
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError

from src.commands.registry import COMMAND_REGISTRY, ArgSpec
from src.exceptions.console_exception import ConsoleInitException
from src.utils import split_cmd


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
        return self.command_defs_by_name.get(command_name)

    def deserialize_args(self, command_def, raw_text):
        if command_def.arg_spec is None:
            arg_spec = ArgSpec.from_signature(command_def.func)
            return arg_spec.parse(raw_text)
        return command_def.arg_spec.parse(raw_text)
```

### decorators.py

```python
from functools import wraps

from prompt_toolkit.completion import Completer
from prompt_toolkit.validation import Validator

from src.commands import BaseCommands
from src.commands.registry import COMMAND_REGISTRY, CommandInfo, CommandStyle, define_command_style
from src.exceptions.console_exception import ConsoleInitException


def commands(commands_cls):
    """Bind a BaseCommands subclass to a Console class for auto command wiring."""
    if not issubclass(commands_cls, BaseCommands):
        raise ConsoleInitException("Commands must inherit BaseCommands")

    def decorator(console_cls):
        from src.consoles import MainConsole, SubConsole
        if not issubclass(console_cls, (MainConsole, SubConsole)):
            raise ConsoleInitException("commands decorator must target a Console class")
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

### registry.py

```python
import re
import enum
import inspect

from prompt_toolkit.completion import Completer
from prompt_toolkit.validation import ValidationError, Validator
from src.exceptions.console_exception import ConsoleInitException
from src.utils.tokenize import tokenize_cmd



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

### general.py

```python
from abc import ABC, abstractmethod

from prompt_toolkit.completion import Completer, WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

from src.commands.registry import ArgSpec


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

### mixins.py

```python
import inspect

from src.ui.output import proxy_print
from src.commands import BaseCommands
from src.commands.decorators import register_command
from src.commands.general import GeneralValidator
from src.exceptions.console_exception import ConsoleExit, SubConsoleExit
from src.utils.table import Table


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
            if issubclass(cls, CommandMixin):
                base_commands_funcs.extend([member[1] for member in inspect.getmembers(cls, inspect.isfunction)])
        for name, func in self.command_funcs.items():
            row = [name, func.info.func_description]
            if func in base_commands_funcs:
                base_funcs.append(row)
            else:
                custom_funcs.append(row)
        if base_funcs:
            proxy_print(Table(header, base_funcs, "Core Commands"))
        if custom_funcs:
            proxy_print(Table(header, custom_funcs, "Custom Commands"))

class DefaultCommands(BaseCommands, HelpMixin, QuitMixin):
    pass
```

### (P)exmaple

#### (M)__init.py\_\_

```python
from src.commands.examples.root_commands import RootCommands
from src.commands.examples.sub_commands import SubCommands

__all__ = [
    "RootCommands",
    "SubCommands",
]
```

#### (M)root_commands.py

```python
from src.commands import BaseCommands
from src.commands.decorators import register_command
from src.commands.general import GeneralValidator
from src.commands.mixins import HelpMixin, QuitMixin
from src.core.events import UIEventLevel
from src.ui.output import proxy_print


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

#### (M)sub_commands.py

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

## consoles

### (M)__init.py\_\_

```python
from src.consoles.core import BaseConsole, MainConsole, SubConsole
from src.consoles.decorators import root, sub, multi
from src.consoles.registry import REGISTRY
from src.consoles.loader import DEFAULT_CONSOLE_MODULES

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

### core.py

```python
import uuid
from abc import ABC

from prompt_toolkit import PromptSession

from src.core.events import UIEventListener, UIEventSpeaker
from src.executor import Invocation
from src.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from src.ui.output import proxy_print
from src.utils import split_cmd


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
        from src.commands import COMMAND_REGISTRY
        commands_cls = getattr(self.__class__, "__commands_cls__", None)
        if commands_cls is None:
            commands = self.init_commands()
            if commands is not None:
                return commands
            commands_cls = COMMAND_REGISTRY.get_commands_cls(self.__class__)
        if commands_cls is None:
            from src.commands.mixins import DefaultCommands
            commands_cls = DefaultCommands
        return commands_cls(self)

    def handler_event(self, event):
        if BaseConsole.forward_console is not None and BaseConsole.forward_console == self:
            proxy_print(event.msg, event.level)

    def run(self, invocation: Invocation):
        command_def = self.commands.get_command_def(invocation.command_id)
        if len(invocation.argv) == 0:
            return command_def.func(self.commands)
        return command_def.func(self.commands, *invocation.argv)

    def execute(self, cmd):
        try:
            invocation, token = self._build_invocation(cmd)
            if invocation is None:
                if token != "":
                    self.cmd_invoke_miss(cmd)
                return
            executor = getattr(self.manager, "executor", None) if self.manager is not None else None
            if executor is None:
                self.run(invocation)
                return
            executor.submit_threadsafe(invocation, handler=self.run)
        except ValueError:
            return

    def _build_invocation(self, cmd):
        token, arg_text, _ = split_cmd(cmd)
        if token == "":
            return None, token
        command_def = self.commands.get_command_def(token)
        if command_def is None:
            return None, token
        param_list = self.commands.deserialize_args(command_def, arg_text)
        invocation = Invocation(
            run_id=str(uuid.uuid4()),
            source="tty",
            console_id=self.uid,
            command_id=token,
            argv=param_list,
            raw_cmd=cmd,
        )
        return invocation, token

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

### decorators.py

```python
from src.consoles.registry import REGISTRY
from src.exceptions.console_exception import ConsoleInitException


def root(console_cls):
    """Mark a MainConsole subclass as the single root console."""
    from src.consoles import MainConsole
    if not issubclass(console_cls, MainConsole):
        raise ConsoleInitException("Root console must inherit MainConsole")
    REGISTRY.set_root(console_cls)
    return console_cls


def sub(parent_name):
    """Register a SubConsole subclass to a single parent console by name."""
    if not isinstance(parent_name, str) or parent_name == "":
        raise ConsoleInitException("Sub console parent name is empty")

    def decorator(console_cls):
        from src.consoles import SubConsole
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
        from src.consoles import SubConsole
        if not issubclass(console_cls, SubConsole):
            raise ConsoleInitException("Multi console must inherit SubConsole")
        REGISTRY.add_multi(console_cls, parent_map)
        return console_cls

    return decorator
```

### registry.py

```python
from src.exceptions.console_exception import ConsoleInitException


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

### loader.py

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

### manager.py

```python
from src.core.events import UIEventLevel, UIEventSpeaker
from src.exceptions.console_exception import ConsoleExit, ConsoleInitException, SubConsoleExit
from src.ui.output import proxy_print


class ConsoleEntry:
    def __init__(self, console_cls, kwargs):
        self.console_cls = console_cls
        self.kwargs = kwargs


class ConsoleManager:
    def __init__(self, service=None, executor=None, on_shutdown=None):
        self._registry = {}
        self._stack = []
        self._console_tree = None
        self._root_name = None
        self._service = service
        self._executor = executor
        self._on_shutdown = on_shutdown
        self._shutdown_called = False
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
        if callable(self._on_shutdown):
            self._on_shutdown()

    def _warn_service_if_needed(self, service):
        if service is not None and not isinstance(service, UIEventSpeaker):
            msg = f"The Service core[{service.__class__}] doesn't extend the [UIEventSpeaker],"\
                  " which may affect the output of the Service core on the UI!"
            proxy_print(msg, UIEventLevel.WARNING)

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
        self._stack.append(console)
        return console

    def pop(self):
        if not self._stack:
            return None
        console = self._stack.pop()
        console.clean_console()
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
        self._stack.append(root_console)
        self._loop()

    def _loop(self):
        try:
            while self._stack:
                try:
                    cmd = self.current.session.prompt()
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
```

### (P)exmaple

#### (M)__init.py\_\_

```python
from src.consoles.examples.root_console import RootConsole
from src.consoles.examples.sub_console import ModuleConsole

__all__ = [
    "RootConsole",
    "ModuleConsole",
]
```

#### (M)root_console.py

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

#### (M)sub_console.py

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

## core

### (M)__init.py\_\_

```python
from src.core.events import UIEvent, UIEventLevel, UIEventListener, UIEventSpeaker

__all__ = [
    "UIEvent",
    "UIEventLevel",
    "UIEventListener",
    "UIEventSpeaker",
]
```

### (M)events.py

```python
import enum


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


class UIEvent:
    def __init__(self, msg, level=UIEventLevel.TEXT, run_id=None, event_type=None, payload=None):
        self.msg = msg
        self.level = level
        self.run_id = run_id
        self.event_type = event_type
        self.payload = payload


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

## exceptions

### (M)__init.py\_\_

```python
class UIBaseException(Exception):
    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    def __str__(self):
        return self.msg
```

### (M)console_exception.py

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

## executor

### (M)__init.py\_\_

```python
from src.executor.executor import CommandExecutor
from src.executor.models import Invocation, RunState, RunStatus

__all__ = [
    "CommandExecutor",
    "Invocation",
    "RunState",
    "RunStatus",
]
```

### (M)executor.py

```python
import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.core.events import UIEvent, UIEventLevel, UIEventSpeaker
from src.executor.models import Invocation, RunState, RunStatus


@dataclass
class WorkItem:
    invocation: Invocation
    handler: Callable[[Invocation], object]


class CommandExecutor(UIEventSpeaker):
    def __init__(self, workers: int = 1, loop=None):
        super().__init__()
        self._worker_count = workers
        self._loop = loop
        self._queue = None
        self._workers = []
        self._locks: Dict[str, asyncio.Lock] = {}
        self._runs: Dict[str, RunState] = {}
        self._event_queues: Dict[str, asyncio.Queue] = {}
        self._run_futures: Dict[str, asyncio.Future] = {}

    @property
    def runs(self):
        return self._runs

    def start(self, loop=None):
        if loop is not None:
            self._loop = loop
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError("Executor start requires a running event loop") from exc
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
        self._runs[run_id] = RunState(run_id=run_id)
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        if self._loop is None or not self._loop.is_running():
            self._run_inline(invocation, handler)
            return run_id
        self.start()
        self._run_futures[run_id] = self._loop.create_future()
        self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))
        return run_id

    async def wait_result(self, run_id: str):
        future = self._run_futures.get(run_id)
        if future is None:
            run_state = self._runs.get(run_id)
            if run_state is None:
                return None
            if run_state.error is not None:
                raise run_state.error
            return run_state.result
        return await future

    def wait_result_sync(self, run_id: str, timeout: Optional[float] = None):
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and running_loop == self._loop:
            raise RuntimeError("wait_result_sync cannot be called from the executor loop thread")
        future = self._run_futures.get(run_id)
        if future is not None and self._loop is not None and self._loop.is_running():
            result_future = asyncio.run_coroutine_threadsafe(self.wait_result(run_id), self._loop)
            return result_future.result(timeout)
        run_state = self._runs.get(run_id)
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

    def stream_events(self, run_id: str):
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        return self._event_queues.setdefault(run_id, asyncio.Queue())

    def publish_event(self, run_id: str, event):
        if getattr(event, "run_id", None) is None:
            event.run_id = run_id
        if self._loop is not None and self._loop.is_running():
            queue = self._event_queues.setdefault(run_id, asyncio.Queue())
            queue.put_nowait(event)
        self.notify_event_listeners(event)

    async def shutdown(self, wait: bool = True):
        workers = list(self._workers)
        self._workers.clear()
        for task in workers:
            task.cancel()
        if wait and workers:
            await asyncio.gather(*workers, return_exceptions=True)

    def shutdown_threadsafe(self, wait: bool = True, timeout: Optional[float] = None):
        loop = self._loop
        if loop is None or not loop.is_running():
            for task in list(self._workers):
                task.cancel()
            self._workers.clear()
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
        self._runs[run_id] = RunState(run_id=run_id)
        if self._loop is None or not self._loop.is_running():
            return self.submit(invocation, handler=handler)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop == self._loop:
            return self.submit(invocation, handler=handler)

        async def _enqueue():
            self.start()
            self._run_futures[run_id] = self._loop.create_future()
            self._queue.put_nowait(WorkItem(invocation=invocation, handler=handler))

        asyncio.run_coroutine_threadsafe(_enqueue(), self._loop).result()
        return run_id

    async def _worker_loop(self):
        while True:
            work_item = await self._queue.get()
            run_state = self._runs.get(work_item.invocation.run_id)
            lock = self._locks.setdefault(work_item.invocation.lock_key, asyncio.Lock())
            async with lock:
                await self._execute_work_item(work_item, run_state)
            self._queue.task_done()

    async def _execute_work_item(self, work_item: WorkItem, run_state: Optional[RunState]):
        if run_state is None:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self.publish_event(run_state.run_id, self._build_run_event("start", UIEventLevel.INFO))
        try:
            result = work_item.handler(work_item.invocation)
            if inspect.isawaitable(result):
                result = await result
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self.publish_event(run_state.run_id, self._build_run_event("success", UIEventLevel.SUCCESS))
            self._resolve_future(run_state, result=result)
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self.publish_event(
                run_state.run_id,
                self._build_run_event("failure", UIEventLevel.ERROR, payload={"error": str(exc)}),
            )
            self._resolve_future(run_state, error=exc)
        finally:
            run_state.finished_at = time.time()

    def _resolve_future(self, run_state: RunState, result=None, error: Optional[BaseException] = None):
        future = self._run_futures.get(run_state.run_id)
        if future is None or future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def _run_inline(self, invocation: Invocation, handler):
        run_state = self._runs.get(invocation.run_id)
        if run_state is None:
            return
        run_state.status = RunStatus.RUNNING
        run_state.started_at = time.time()
        self.publish_event(run_state.run_id, self._build_run_event("start", UIEventLevel.INFO))
        try:
            result = handler(invocation)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            run_state.result = result
            run_state.status = RunStatus.SUCCEEDED
            self.publish_event(run_state.run_id, self._build_run_event("success", UIEventLevel.SUCCESS))
        except Exception as exc:
            run_state.error = exc
            run_state.status = RunStatus.FAILED
            self.publish_event(
                run_state.run_id,
                self._build_run_event("failure", UIEventLevel.ERROR, payload={"error": str(exc)}),
            )
        finally:
            run_state.finished_at = time.time()

    @staticmethod
    def _build_run_event(event_type: str, level: UIEventLevel, payload=None):
        return UIEvent(msg=event_type, level=level, event_type=event_type, payload=payload)

    @staticmethod
    def _missing_handler(invocation: Invocation):
        raise RuntimeError("No handler provided for invocation execution")
```

### (M)model.py

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
    argv: List[str] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    lock_key: str = "global"
    timeout_ms: Optional[int] = None
    audit_policy: Optional[str] = None
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

## ui

### (M)__init.py\_\_

```python
from src.ui.output import proxy_print

__all__ = [
    "proxy_print",
]
```

### (M)output.py

```python
from prompt_toolkit import print_formatted_text
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style

from src.core.events import UIEventLevel


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


def proxy_print(text="", text_type=UIEventLevel.TEXT):
    session = get_app_session()
    if text_type == UIEventLevel.TEXT:
        print_formatted_text(text, output=session.output)
        return
    formatted_text = FormattedText([
        ('class:level', MSG_LEVEL_SYMBOL[text_type.value]),
        ('class:text', text)
    ])
    style = Style.from_dict({
        'level': MSG_LEVEL_SYMBOL_STYLE[text_type.value]
    })
    print_formatted_text(formatted_text, style=style, output=session.output)
```

## utils

### (M)__init.py\_\_

```python
from src.utils.table import Table
from src.utils.tokenize import get_command_token, get_func_param_strs, split_cmd, tokenize_cmd
from src.utils.ui_logger import ConsoleHandler

__all__ = [
    "ConsoleHandler",
    "Table",
    "get_command_token",
    "get_func_param_strs",
    "split_cmd",
    "tokenize_cmd",
]
```

### (M)table.py

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

### (M)tokenize.py

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

### (M)ui_logger.py

```python
import logging

from src.core.events import UIEventLevel
from src.ui.output import proxy_print


class ConsoleHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            log = self.format(record)
            proxy_print(log, UIEventLevel.DEBUG)
        except Exception:
            self.handleError(record)
```

