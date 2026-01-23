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

