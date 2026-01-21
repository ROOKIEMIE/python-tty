import enum
import inspect
import re
from functools import wraps

from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.validation import DummyValidator, Validator, ValidationError

from src.commands.registry import COMMAND_REGISTRY, define_command_style
from src.exceptions.console_exception import ConsoleInitException
from src.utils import get_command_token, cmd_split_type


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
        text = text.strip()
        if text == "":
            return []
        if self.max_args == 1:
            return [text]
        return text.split(cmd_split_type)

    def count_args(self, text):
        text = text.strip()
        if text == "":
            return 0
        if self.max_args == 1:
            return 1
        return text.count(cmd_split_type) + 1

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


class GeneralValidator(Validator):
    def __init__(self, console, func, arg_spec=None):
        self.console = console
        self.func = func
        self.arg_spec = arg_spec or ArgSpec.from_signature(func)
        super().__init__()

    def validate(self, document: Document) -> None:
        self.argument_count_validate(document.text)
        self.custom_validate(document.text)

    def custom_validate(self, text: str):
        pass

    def argument_count_validate(self, text):
        try:
            count = self.arg_spec.count_args(text)
            self.arg_spec.validate_count(count)
        except ValueError:
            return


class CommandValidator(Validator):
    def __init__(self, command_validators: dict, enable_undefined_command=False):
        self.command_validators = command_validators
        self.enable_undefined_command = enable_undefined_command
        super().__init__()

    def validate(self, document: Document) -> None:
        try:
            cmd = document.text.strip()
            token = get_command_token(cmd)
            if token in self.command_validators.keys():
                cmd_validator = self.command_validators[token]
                cmd_validator.validate(Document(text=cmd[len(token)+1:]))
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
                self.command_completers[command_name] = command_def.completer(self.console)
            self.command_validators[command_name] = self._build_validator(command_def)

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


